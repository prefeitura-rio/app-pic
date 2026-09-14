import io

import polars as pl
from fastapi import HTTPException, UploadFile

from src.api.v1.queries import GOVERNANCE_TABLE_QUERY
from src.config import env
from src.core.security.jwt import CurrentUserPermissions
from src.pic.domain.models.admin import (
    BatchImportError,
    BatchImportResult,
    BatchPermissionsError,
    BatchPermissionsRequest,
    BatchPermissionsResult,
    ImportedUser,
)
from src.pic.infrastructure.admin.governance_cache import refresh_governance_cache
from src.pic.infrastructure.admin.id_utils import _convert_id_list_to_bq_struct
from src.pic.infrastructure.admin.validation import (
    _sanitize_cpf,
    _validate_cpf,
    calculate_permission,
    require_admin,
    validate_equipment_secretaria_consistency,
    validate_secretaria_acesso_permission,
    validate_segmented_admin_can_manage,
)
from src.utils.bigquery import execute_query
from src.utils.data_manager import DataManager
from src.utils.log import logger

PROJECT_ID = env.BQ_PROJECT_ID
DATASET_ID = env.BQ_DATASET_ID
TABLE_ID_DATA_ACCESS = env.BQ_TABLE_ID_DATA_ACCESS


async def batch_import_users_data(
    permissions: CurrentUserPermissions,
    file: UploadFile,
) -> BatchImportResult:
    require_admin(permissions)

    logger.info(f"Iniciando importacao em batch - arquivo: {file.filename}")

    if not file.filename:
        raise HTTPException(status_code=400, detail="Nome do arquivo nao informado")

    filename_lower = file.filename.lower()
    if not (filename_lower.endswith(".csv") or filename_lower.endswith(".xlsx")):
        raise HTTPException(status_code=400, detail="Formato de arquivo invalido. Use CSV ou XLSX.")

    try:
        content = await file.read()

        if filename_lower.endswith(".csv"):
            try:
                df = pl.read_csv(io.BytesIO(content))
            except Exception:
                df = pl.read_csv(io.BytesIO(content), encoding="latin1")
        else:
            import openpyxl  # noqa: F401
            import pandas as pd
            pd_df = pd.read_excel(io.BytesIO(content), engine="openpyxl")
            df = pl.from_pandas(pd_df)

        logger.info(f"Arquivo lido: {len(df)} linhas, colunas: {df.columns}")

        if "cpf" not in df.columns:
            raise HTTPException(status_code=400, detail="Coluna 'cpf' nao encontrada no arquivo")

        if len(df) > 1000:
            raise HTTPException(status_code=400, detail=f"Arquivo contem {len(df)} linhas. Maximo permitido: 1000")

        governance_df, _, _ = await DataManager.get_dataset(GOVERNANCE_TABLE_QUERY)
        existing_cpfs = set(governance_df["cpf"].to_list())

        errors: list[BatchImportError] = []
        imported_users: list[ImportedUser] = []

        for row_idx, row in enumerate(df.to_dicts(), start=1):
            cpf_raw = row.get("cpf", "")
            cpf_raw_str = str(cpf_raw) if cpf_raw is not None else ""
            cpf = _sanitize_cpf(cpf_raw_str)

            cpf_error = _validate_cpf(cpf)
            if cpf_error:
                errors.append(BatchImportError(row=row_idx, cpf=cpf_raw_str, error=cpf_error))
                imported_users.append(ImportedUser(
                    cpf=cpf_raw_str or "", nome=row.get("nome"), email=row.get("email"),
                    ocupacao=row.get("ocupacao"), secretaria=row.get("secretaria"),
                    status="error", error_message=cpf_error,
                ))
                continue

            if cpf in existing_cpfs:
                existing_user_row = governance_df.filter(pl.col("cpf") == cpf)
                existing_perms = {}
                if not existing_user_row.is_empty():
                    user_dict = existing_user_row.row(0, named=True)
                    existing_perms = {
                        "is_admin": user_dict.get("is_admin", False),
                        "is_super_admin": user_dict.get("is_super_admin", False),
                        "id_cras_list": user_dict.get("id_cras_list"),
                        "id_escola_list": user_dict.get("id_escola_list"),
                        "id_cre_list": user_dict.get("id_cre_list"),
                        "id_ap_list": user_dict.get("id_ap_list"),
                        "id_cas_list": user_dict.get("id_cas_list"),
                        "id_clinica_familia_list": user_dict.get("id_clinica_familia_list"),
                        "secretaria_acesso": user_dict.get("secretaria_acesso"),
                    }

                imported_users.append(ImportedUser(
                    cpf=cpf,
                    nome=row.get("nome") or user_dict.get("nome"),
                    email=row.get("email") or user_dict.get("email"),
                    ocupacao=row.get("ocupacao") or user_dict.get("ocupacao"),
                    secretaria=row.get("secretaria") or user_dict.get("secretaria"),
                    status="exists",
                    **existing_perms,
                ))
                continue

            imported_users.append(ImportedUser(
                cpf=cpf, nome=row.get("nome"), email=row.get("email"),
                ocupacao=row.get("ocupacao"), secretaria=row.get("secretaria"),
                status="new",
            ))

        new_count = len([u for u in imported_users if u.status == "new"])

        return BatchImportResult(
            total=len(df),
            imported=new_count,
            skipped=len([u for u in imported_users if u.status == "exists"]),
            errors=errors,
            imported_users=imported_users,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro na importacao em batch: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def batch_update_permissions_data(
    permissions: CurrentUserPermissions,
    request: BatchPermissionsRequest,
) -> BatchPermissionsResult:
    require_admin(permissions)

    if not request.users:
        raise HTTPException(status_code=400, detail="Lista de usuarios vazia")

    logger.info(f"Atualizando permissoes em batch para {len(request.users)} usuarios (MERGE)")

    target_ids_dict = {
        "id_cras_list": request.id_cras_list,
        "id_escola_list": request.id_escola_list,
        "id_cre_list": request.id_cre_list,
        "id_ap_list": request.id_ap_list,
        "id_cas_list": request.id_cas_list,
        "id_clinica_familia_list": request.id_clinica_familia_list,
        "id_equipe_familia_list": request.id_equipe_familia_list,
    }
    target_ids_to_validate = {k: v for k, v in target_ids_dict.items() if v is not None}

    if target_ids_to_validate:
        validate_segmented_admin_can_manage(permissions, target_ids_to_validate)
    if request.secretaria_acesso is not None:
        validate_secretaria_acesso_permission(permissions, request.secretaria_acesso)
    validate_equipment_secretaria_consistency(target_ids_dict, request.secretaria_acesso)

    permission_value = calculate_permission(request.is_admin, False)

    id_cras_sql = _convert_id_list_to_bq_struct(request.id_cras_list)
    id_escola_sql = _convert_id_list_to_bq_struct(request.id_escola_list)
    id_cre_sql = _convert_id_list_to_bq_struct(request.id_cre_list)
    id_ap_sql = _convert_id_list_to_bq_struct(request.id_ap_list)
    id_cas_sql = _convert_id_list_to_bq_struct(request.id_cas_list)
    id_clinica_sql = _convert_id_list_to_bq_struct(request.id_clinica_familia_list)
    id_equipe_familia_sql = _convert_id_list_to_bq_struct(request.id_equipe_familia_list)

    if not request.secretaria_acesso or request.secretaria_acesso == "NULL":
        secretaria_acesso_sql = "NULL"
    else:
        secretaria_acesso_sql = f"'{request.secretaria_acesso}'"

    errors: list[BatchPermissionsError] = []
    valid_users: list[dict] = []
    cpf_to_user_data: dict = {}

    for user_data in request.users:
        cpf = _sanitize_cpf(user_data.cpf)
        if not cpf or len(cpf) != 11:
            errors.append(BatchPermissionsError(cpf=user_data.cpf, error="CPF invalido"))
            continue
        cpf_to_user_data[cpf] = user_data

    cpfs_to_check = list(cpf_to_user_data.keys())
    existing_users: dict = {}

    if cpfs_to_check:
        cpf_list_sql = ", ".join([f"'{cpf}'" for cpf in cpfs_to_check])
        check_query = f"SELECT cpf, is_admin, is_super_admin FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID_DATA_ACCESS}` WHERE cpf IN ({cpf_list_sql})"
        result_df = execute_query(check_query)
        if not result_df.is_empty():
            for row in result_df.iter_rows(named=True):
                existing_users[row["cpf"]] = {
                    "is_admin": row.get("is_admin", False) or False,
                    "is_super_admin": row.get("is_super_admin", False) or False,
                }

    for cpf, user_data in cpf_to_user_data.items():
        if cpf in existing_users:
            target_user = existing_users[cpf]
            if permissions.is_super_admin and target_user["is_super_admin"]:
                errors.append(BatchPermissionsError(cpf=cpf, error="Super admins nao podem editar outros super admins"))
                continue
            if not permissions.is_super_admin and (target_user["is_admin"] or target_user["is_super_admin"]):
                errors.append(BatchPermissionsError(cpf=cpf, error="Admins nao podem editar outros admins ou super admins"))
                continue

        def escape_sql(val: str | None) -> str:
            if val is None:
                return "NULL"
            return f"'{val.replace('\'', '\\\'')}'"

        valid_users.append({
            "cpf": cpf,
            "nome": escape_sql(user_data.nome),
            "email": escape_sql(user_data.email),
            "ocupacao": escape_sql(user_data.ocupacao),
            "secretaria": escape_sql(user_data.secretaria),
        })

    if not valid_users:
        return BatchPermissionsResult(total=len(request.users), updated=0, errors=errors)

    source_rows = [
        f"SELECT '{u['cpf']}' as cpf, {u['nome']} as nome, {u['email']} as email, {u['ocupacao']} as ocupacao, {u['secretaria']} as secretaria"
        for u in valid_users
    ]
    source_query = " UNION ALL ".join(source_rows)

    merge_query = f"""
    MERGE `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID_DATA_ACCESS}` AS T
    USING ({source_query}) AS S
    ON T.cpf = S.cpf
    WHEN MATCHED THEN
        UPDATE SET
            is_admin = {str(request.is_admin).upper()},
            permission = '{permission_value}',
            id_cras_list = {id_cras_sql},
            id_escola_list = {id_escola_sql},
            id_cre_list = {id_cre_sql},
            id_ap_list = {id_ap_sql},
            id_cas_list = {id_cas_sql},
            id_clinica_familia_list = {id_clinica_sql},
            id_equipe_familia_list = {id_equipe_familia_sql},
            secretaria_acesso = {secretaria_acesso_sql},
            nome = COALESCE(S.nome, T.nome),
            email = COALESCE(S.email, T.email),
            ocupacao = COALESCE(S.ocupacao, T.ocupacao),
            secretaria = COALESCE(S.secretaria, T.secretaria),
            updated_by = '{permissions.cpf}',
            updated_at = CURRENT_TIMESTAMP()
    WHEN NOT MATCHED THEN
        INSERT (cpf, nome, email, ocupacao, secretaria, is_admin, is_super_admin, permission,
                id_cras_list, id_escola_list, id_cre_list, id_ap_list, id_cas_list, id_clinica_familia_list, id_equipe_familia_list,
                secretaria_acesso, notes, active, created_at, updated_at, created_by, updated_by)
        VALUES (S.cpf, S.nome, S.email, S.ocupacao, S.secretaria, {str(request.is_admin).upper()},
                FALSE, '{permission_value}',
                {id_cras_sql}, {id_escola_sql}, {id_cre_sql}, {id_ap_sql}, {id_cas_sql}, {id_clinica_sql}, {id_equipe_familia_sql},
                {secretaria_acesso_sql}, NULL, TRUE, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP(),
                '{permissions.cpf}', '{permissions.cpf}')
    """

    try:
        logger.info(f"Executando MERGE para {len(valid_users)} usuarios...")
        execute_query(merge_query)
        logger.info("MERGE executado com sucesso")
    except Exception as e:
        logger.error(f"Erro no MERGE: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao processar batch: {str(e)}")

    refresh_governance_cache()

    return BatchPermissionsResult(
        total=len(request.users),
        updated=len(valid_users),
        errors=errors,
    )
