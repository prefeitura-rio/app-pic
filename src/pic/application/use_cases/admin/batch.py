from typing import Any

import polars as pl

from src.core.security.jwt import CurrentUserPermissionsV2
from src.pic.application.ports.admin_repository import IAdminRepository
from src.pic.application.ports.user_import_parser import IUserImportFileParser
from src.pic.application.use_cases.admin.validation import (
    _sanitize_cpf,
    _validate_cpf,
    require_admin,
    validate_equipment_secretaria_consistency,
    validate_secretarias_acesso_permission,
    validate_segmented_admin_can_manage,
)
from src.pic.domain.errors import ValidationError
from src.pic.domain.models.admin import (
    BatchImportError,
    BatchImportResult,
    BatchPermissionsError,
    BatchPermissionsRequest,
    BatchPermissionsResult,
    ImportedUser,
    calculate_permission,
)
from src.utils.log import logger


class BatchImportUsersUseCase:
    def __init__(
        self,
        repository: IAdminRepository,
        parser: IUserImportFileParser,
    ):
        self._repo = repository
        self._parser = parser

    async def execute(
        self,
        permissions: CurrentUserPermissionsV2,
        filename: str | None,
        content: bytes,
        user_token: str | None = None,
    ) -> BatchImportResult:
        require_admin(permissions)

        logger.info(f"Iniciando importacao em batch - arquivo: {filename}")

        df = self._parser.parse(filename or "", content)

        logger.info(f"Arquivo lido: {len(df)} linhas, colunas: {df.columns}")

        governance_df, _, _ = await self._repo.fetch_governance_df()
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
                existing_perms: dict[str, Any] = {}
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
                        "id_equipe_familia_list": user_dict.get("id_equipe_familia_list"),
                        "secretarias_acesso": user_dict.get("secretarias_acesso"),
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


class BatchUpdatePermissionsUseCase:
    def __init__(self, repository: IAdminRepository):
        self._repo = repository

    async def execute(
        self,
        permissions: CurrentUserPermissionsV2,
        request: BatchPermissionsRequest,
    ) -> BatchPermissionsResult:
        require_admin(permissions)

        if not request.users:
            raise ValidationError("Lista de usuarios vazia")

        logger.info(f"Atualizando permissoes em batch para {len(request.users)} usuarios")

        target_ids_dict: dict[str, Any] = {
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
        if request.secretarias_acesso is not None:
            validate_secretarias_acesso_permission(permissions, request.secretarias_acesso)
        validate_equipment_secretaria_consistency(target_ids_dict, request.secretarias_acesso)

        permission_value = calculate_permission(request.is_admin, False)

        errors: list[BatchPermissionsError] = []
        cpf_to_user_data: dict[str, Any] = {}

        for user_data in request.users:
            cpf = _sanitize_cpf(user_data.cpf)
            if not cpf or len(cpf) != 11:
                errors.append(BatchPermissionsError(cpf=user_data.cpf, error="CPF invalido"))
                continue
            cpf_to_user_data[cpf] = user_data

        cpfs_to_check = list(cpf_to_user_data.keys())
        existing_users: dict[str, dict[str, bool]] = {}

        if cpfs_to_check:
            result_df = await self._repo.find_users_by_cpfs(cpfs_to_check)
            if not result_df.is_empty():
                for row in result_df.iter_rows(named=True):
                    existing_users[row["cpf"]] = {
                        "is_admin": row.get("is_admin", False) or False,
                        "is_super_admin": row.get("is_super_admin", False) or False,
                    }

        valid_users: list[dict[str, Any]] = []

        for cpf, user_data in cpf_to_user_data.items():
            if cpf in existing_users:
                target_user = existing_users[cpf]
                if permissions.is_super_admin and target_user["is_super_admin"]:
                    errors.append(BatchPermissionsError(cpf=cpf, error="Super admins nao podem editar outros super admins"))
                    continue
                if not permissions.is_super_admin and (target_user["is_admin"] or target_user["is_super_admin"]):
                    errors.append(BatchPermissionsError(cpf=cpf, error="Admins nao podem editar outros admins ou super admins"))
                    continue

            valid_users.append({
                "cpf": cpf,
                "nome": user_data.nome,
                "email": user_data.email,
                "ocupacao": user_data.ocupacao,
                "secretaria": user_data.secretaria,
            })

        if not valid_users:
            return BatchPermissionsResult(total=len(request.users), updated=0, errors=errors)

        id_lists = {
            "id_cras_list": request.id_cras_list,
            "id_escola_list": request.id_escola_list,
            "id_cre_list": request.id_cre_list,
            "id_ap_list": request.id_ap_list,
            "id_cas_list": request.id_cas_list,
            "id_clinica_familia_list": request.id_clinica_familia_list,
            "id_equipe_familia_list": request.id_equipe_familia_list,
        }

        await self._repo.batch_merge_permissions(
            valid_users=valid_users,
            is_admin=request.is_admin,
            permission=permission_value,
            id_lists=id_lists,
            secretarias_acesso=request.secretarias_acesso,
            updated_by=permissions.cpf,
        )

        return BatchPermissionsResult(
            total=len(request.users),
            updated=len(valid_users),
            errors=errors,
        )
