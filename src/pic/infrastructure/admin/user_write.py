import time as time_module

import polars as pl
from fastapi import HTTPException
from google.cloud import bigquery

from src.api.v1.queries import GOVERNANCE_TABLE_QUERY
from src.config import env
from src.core.security.jwt import CurrentUserPermissions
from src.core.security.permissions_models import IdWithName
from src.pic.domain.models.admin import UpsertUserRequest, UserAccessRecord
from src.pic.infrastructure.admin.governance_cache import refresh_governance_cache
from src.pic.infrastructure.admin.id_utils import _convert_id_list_to_bq_struct
from src.pic.infrastructure.admin.validation import (
    calculate_permission,
    require_admin,
    validate_equipment_secretaria_consistency,
    validate_secretaria_acesso_permission,
    validate_segmented_admin_can_manage,
)
from src.utils.bigquery import build_update_query, execute_query
from src.utils.data_manager import DataManager
from src.utils.log import logger

PROJECT_ID = env.BQ_PROJECT_ID
DATASET_ID = env.BQ_DATASET_ID
TABLE_ID_DATA_ACCESS = env.BQ_TABLE_ID_DATA_ACCESS


async def upsert_user_data(
    permissions: CurrentUserPermissions,
    cpf: str,
    request: UpsertUserRequest,
) -> UserAccessRecord:
    require_admin(permissions)

    if len(cpf) != 11 or not cpf.isdigit():
        raise HTTPException(status_code=400, detail="CPF deve conter exatamente 11 digitos")

    logger.info("Admin fazendo upsert de usuario")
    logger.info(f"  - is_admin: {request.is_admin}, is_super_admin: {request.is_super_admin}")
    logger.info(f"  - active: {request.active}, is_update: {request.is_update}")

    governance_df, _, _ = await DataManager.get_dataset(GOVERNANCE_TABLE_QUERY)
    existing_user = governance_df.filter(pl.col("cpf") == cpf)
    user_exists = not existing_user.is_empty()

    if user_exists:
        existing_row = existing_user.row(0, named=True)
        is_target_super_admin = bool(existing_row.get("is_super_admin", False))
        is_target_admin = bool(existing_row.get("is_admin", False))

        if is_target_super_admin:
            raise HTTPException(status_code=403, detail="Super admins nao podem ser editados")

        if is_target_admin and not permissions.is_super_admin:
            raise HTTPException(status_code=403, detail="Admins nao podem editar outros admins")

        if not permissions.is_super_admin:
            from src.utils.constants import SECRETARIA_NULL, SECRETARIA_TODOS
            admin_secretaria = permissions.secretaria_acesso
            target_secretaria = existing_row.get("secretaria_acesso")

            if admin_secretaria == SECRETARIA_NULL or not admin_secretaria:
                can_edit = target_secretaria is None or target_secretaria == SECRETARIA_NULL
                if not can_edit:
                    raise HTTPException(status_code=403, detail="Voce nao tem acesso a protocolos e so pode gerenciar usuarios sem acesso (NULL).")
            elif admin_secretaria not in [SECRETARIA_TODOS]:
                can_edit = target_secretaria == admin_secretaria or target_secretaria is None or target_secretaria == SECRETARIA_NULL
                if not can_edit:
                    raise HTTPException(status_code=403, detail=f"Voce nao pode editar usuarios de outras secretarias. Voce tem acesso apenas a {admin_secretaria}.")

    if cpf == permissions.cpf:
        raise HTTPException(status_code=403, detail="Voce nao pode editar suas proprias permissoes")

    if request.is_super_admin and not permissions.is_super_admin:
        raise HTTPException(status_code=403, detail="Apenas super admins podem criar ou promover outros super admins")

    if request.is_super_admin:
        raise HTTPException(status_code=403, detail="Criacao de super admins nao e permitida via interface")

    target_ids_dict = request.model_dump(
        include={"id_cras_list", "id_escola_list", "id_cre_list", "id_ap_list", "id_cas_list", "id_clinica_familia_list", "id_equipe_familia_list"},
        exclude_unset=True,
    )
    target_ids_to_validate = {k: v for k, v in target_ids_dict.items() if v is not None}

    if target_ids_to_validate:
        validate_segmented_admin_can_manage(permissions, target_ids_to_validate)
    if request.secretaria_acesso is not None:
        validate_secretaria_acesso_permission(permissions, request.secretaria_acesso)
    validate_equipment_secretaria_consistency(target_ids_dict, request.secretaria_acesso)

    try:
        if user_exists:
            update_dict = {}
            struct_updates = []

            if request.email is not None:
                update_dict["email"] = request.email
            if request.nome is not None:
                update_dict["nome"] = request.nome
            if request.ocupacao is not None:
                update_dict["ocupacao"] = request.ocupacao
            if request.secretaria is not None:
                update_dict["secretaria"] = request.secretaria
            if request.secretaria_acesso is not None:
                update_dict["secretaria_acesso"] = None if request.secretaria_acesso == "NULL" else request.secretaria_acesso

            is_full_update = (
                request.email is not None or request.nome is not None
                or request.ocupacao is not None or request.secretaria is not None
                or request.secretaria_acesso is not None
                or request.id_cras_list is not None or request.id_escola_list is not None
            )

            if is_full_update:
                update_dict["is_admin"] = request.is_admin
                update_dict["is_super_admin"] = request.is_super_admin
                update_dict["permission"] = calculate_permission(request.is_admin, request.is_super_admin)

                struct_updates = [
                    f"id_cras_list = {_convert_id_list_to_bq_struct(request.id_cras_list)}",
                    f"id_escola_list = {_convert_id_list_to_bq_struct(request.id_escola_list)}",
                    f"id_cre_list = {_convert_id_list_to_bq_struct(request.id_cre_list)}",
                    f"id_ap_list = {_convert_id_list_to_bq_struct(request.id_ap_list)}",
                    f"id_cas_list = {_convert_id_list_to_bq_struct(request.id_cas_list)}",
                    f"id_clinica_familia_list = {_convert_id_list_to_bq_struct(request.id_clinica_familia_list)}",
                    f"id_equipe_familia_list = {_convert_id_list_to_bq_struct(request.id_equipe_familia_list)}",
                ]

            if request.notes is not None:
                update_dict["notes"] = request.notes

            update_dict["active"] = request.active
            update_dict["updated_by"] = permissions.cpf

            if not update_dict and not struct_updates:
                return UserAccessRecord(**existing_user.row(0, named=True))

            if update_dict:
                query, parameters = build_update_query(
                    table=f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID_DATA_ACCESS}",
                    updates=update_dict,
                    where_field="cpf",
                    where_value=cpf,
                )
                if struct_updates:
                    query_parts = query.split("WHERE")
                    set_clause = query_parts[0].rstrip()
                    set_clause += ",\n        " + ",\n        ".join(struct_updates)
                    set_clause += ",\n        updated_at = CURRENT_TIMESTAMP()"
                    query = set_clause + "\n    WHERE" + query_parts[1]
                else:
                    query_parts = query.split("WHERE")
                    set_clause = query_parts[0].rstrip()
                    set_clause += ",\n        updated_at = CURRENT_TIMESTAMP()"
                    query = set_clause + "\n    WHERE" + query_parts[1]
            else:
                all_updates = struct_updates + ["updated_at = CURRENT_TIMESTAMP()"]
                query = f"UPDATE `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID_DATA_ACCESS}` SET {', '.join(all_updates)} WHERE cpf = @cpf"
                parameters = [bigquery.ScalarQueryParameter("cpf", "STRING", cpf)]

            execute_query(query, parameters)
            logger.info("Usuario atualizado")

        else:
            permission_value = calculate_permission(request.is_admin, request.is_super_admin)

            query = f"""
            INSERT INTO `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID_DATA_ACCESS}`
            (cpf, email, nome, ocupacao, secretaria, is_admin, is_super_admin, permission,
             id_cras_list, id_escola_list, id_cre_list, id_ap_list, id_cas_list, id_clinica_familia_list, id_equipe_familia_list,
             secretaria_acesso, created_by, active, notes, created_at)
            VALUES (@cpf, @email, @nome, @ocupacao, @secretaria, @is_admin, @is_super_admin, @permission,
             {_convert_id_list_to_bq_struct(request.id_cras_list)},
             {_convert_id_list_to_bq_struct(request.id_escola_list)},
             {_convert_id_list_to_bq_struct(request.id_cre_list)},
             {_convert_id_list_to_bq_struct(request.id_ap_list)},
             {_convert_id_list_to_bq_struct(request.id_cas_list)},
             {_convert_id_list_to_bq_struct(request.id_clinica_familia_list)},
             {_convert_id_list_to_bq_struct(request.id_equipe_familia_list)},
             @secretaria_acesso, @created_by, @active, @notes, CURRENT_TIMESTAMP())
            """

            secretaria_acesso_value = None if request.secretaria_acesso == "NULL" else request.secretaria_acesso

            parameters = [
                bigquery.ScalarQueryParameter("cpf", "STRING", cpf),
                bigquery.ScalarQueryParameter("email", "STRING", request.email),
                bigquery.ScalarQueryParameter("nome", "STRING", request.nome),
                bigquery.ScalarQueryParameter("ocupacao", "STRING", request.ocupacao),
                bigquery.ScalarQueryParameter("secretaria", "STRING", request.secretaria),
                bigquery.ScalarQueryParameter("is_admin", "BOOL", request.is_admin),
                bigquery.ScalarQueryParameter("is_super_admin", "BOOL", request.is_super_admin),
                bigquery.ScalarQueryParameter("permission", "STRING", permission_value),
                bigquery.ScalarQueryParameter("secretaria_acesso", "STRING", secretaria_acesso_value),
                bigquery.ScalarQueryParameter("created_by", "STRING", permissions.cpf),
                bigquery.ScalarQueryParameter("active", "BOOL", request.active),
                bigquery.ScalarQueryParameter("notes", "STRING", request.notes),
            ]

            execute_query(query, parameters)
            logger.info("Usuario criado")

        refresh_governance_cache()
        time_module.sleep(0.1)

        governance_df, _, _ = await DataManager.get_dataset(GOVERNANCE_TABLE_QUERY, bypass_cache=True)
        user_row = governance_df.filter(pl.col("cpf") == cpf)

        if user_row.is_empty():
            raise HTTPException(status_code=500, detail=f"Usuario {cpf} salvo, mas nao encontrado no cache renovado")

        row_dict = user_row.row(0, named=True)

        if "active" in row_dict:
            row_dict["active"] = bool(row_dict["active"])
        if "is_admin" in row_dict:
            row_dict["is_admin"] = bool(row_dict["is_admin"])
        if "is_super_admin" in row_dict:
            row_dict["is_super_admin"] = bool(row_dict["is_super_admin"])

        if "created_at" in row_dict and hasattr(row_dict["created_at"], "to_pydatetime"):
            row_dict["created_at"] = row_dict["created_at"].to_pydatetime()
        if "updated_at" in row_dict and hasattr(row_dict["updated_at"], "to_pydatetime"):
            row_dict["updated_at"] = row_dict["updated_at"].to_pydatetime()

        for id_type in ["id_cras", "id_escola", "id_cre", "id_ap", "id_cas", "id_clinica_familia", "id_equipe_familia"]:
            list_key = f"{id_type}_list"
            if row_dict.get(list_key) is not None and isinstance(row_dict[list_key], list):
                row_dict[list_key] = [
                    IdWithName(**item) if isinstance(item, dict) else item
                    for item in row_dict[list_key]
                ]

        return UserAccessRecord(**row_dict)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao fazer upsert do usuario {cpf}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def delete_user_data(permissions: CurrentUserPermissions, cpf: str) -> None:
    require_admin(permissions)

    governance_df, _, _ = await DataManager.get_dataset(GOVERNANCE_TABLE_QUERY)
    existing_user = governance_df.filter(pl.col("cpf") == cpf)

    if existing_user.is_empty():
        raise HTTPException(status_code=404, detail=f"Usuario {cpf} nao encontrado")

    existing_row = existing_user.row(0, named=True)
    is_target_super_admin = bool(existing_row.get("is_super_admin", False))
    is_target_admin = bool(existing_row.get("is_admin", False))

    if is_target_super_admin:
        raise HTTPException(status_code=403, detail="Super admins nao podem ser deletados")

    if is_target_admin and not permissions.is_super_admin:
        raise HTTPException(status_code=403, detail="Admins nao podem deletar outros admins")

    if not permissions.is_super_admin:
        from src.utils.constants import SECRETARIA_NULL, SECRETARIA_TODOS
        admin_secretaria = permissions.secretaria_acesso
        target_secretaria = existing_row.get("secretaria_acesso")

        if admin_secretaria == SECRETARIA_NULL or not admin_secretaria:
            can_delete = target_secretaria is None or target_secretaria == SECRETARIA_NULL
            if not can_delete:
                raise HTTPException(status_code=403, detail="Voce nao tem acesso a protocolos e so pode gerenciar usuarios sem acesso (NULL).")
        elif admin_secretaria not in [SECRETARIA_TODOS]:
            can_delete = target_secretaria == admin_secretaria or target_secretaria is None or target_secretaria == SECRETARIA_NULL
            if not can_delete:
                raise HTTPException(status_code=403, detail=f"Voce nao pode deletar usuarios de outras secretarias. Voce tem acesso apenas a {admin_secretaria}.")

    if cpf == permissions.cpf:
        raise HTTPException(status_code=403, detail="Voce nao pode deletar a si mesmo")

    query = f"""
    UPDATE `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID_DATA_ACCESS}`
    SET active = @active, updated_by = @updated_by, updated_at = CURRENT_TIMESTAMP()
    WHERE cpf = @cpf
    """

    parameters = [
        bigquery.ScalarQueryParameter("active", "BOOL", False),
        bigquery.ScalarQueryParameter("updated_by", "STRING", permissions.cpf),
        bigquery.ScalarQueryParameter("cpf", "STRING", cpf),
    ]

    try:
        execute_query(query, parameters)
        logger.info("Usuario marcado como inativo")
        refresh_governance_cache()
    except Exception as e:
        logger.error(f"Erro ao deletar usuario: {e}")
        raise HTTPException(status_code=500, detail=str(e))
