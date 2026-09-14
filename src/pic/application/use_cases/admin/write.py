from typing import Any

import polars as pl

from src.core.security.jwt import CurrentUserPermissionsV2
from src.pic.application.ports.admin_repository import IAdminRepository
from src.pic.application.use_cases.admin.id_utils import (
    build_user_access_record,
    df_to_json,
)
from src.pic.application.use_cases.admin.validation import (
    _filter_manageable_users,
    require_admin,
    validate_equipment_secretaria_consistency,
    validate_secretarias_acesso_permission,
    validate_segmented_admin_can_manage,
)
from src.pic.domain.errors import ForbiddenError, NotFoundError, ValidationError
from src.pic.domain.models.admin import (
    IdWithName,
    UpsertUserRequest,
    UserAccessRecord,
    calculate_permission,
)
from src.pic.domain.models.filters import USER_FILTER_OPTIONS_CONFIG, FilterOption
from src.pic.domain.models.pagination import PaginationMeta, PaginationParams
from src.utils.constants import SECRETARIA_LABELS
from src.utils.log import logger


class ListUsersUseCase:
    def __init__(self, repository: IAdminRepository):
        self._repo = repository

    async def execute(
        self,
        permissions: CurrentUserPermissionsV2,
        pagination: PaginationParams,
        active: bool | None = None,
        ocupacao: str | None = None,
        secretaria: str | None = None,
        permission: str | None = None,
        secretarias_acesso: list[str] | None = None,
        search: str | None = None,
        bypass_cache: bool = False,
        user_token: str | None = None,
    ):
        require_admin(permissions)

        filters_dict: dict[str, Any] = {}
        if active is not None:
            filters_dict["active"] = active
        if ocupacao:
            filters_dict["ocupacao"] = ocupacao
        if secretaria:
            filters_dict["secretaria"] = secretaria
        if permission:
            filters_dict["permission"] = permission
        if secretarias_acesso:
            filters_dict["secretarias_acesso"] = secretarias_acesso

        df_data, meta, filter_options = await self._repo.find_paginated_users(
            filters_dict=filters_dict,
            page=pagination.page,
            page_size=pagination.page_size,
            search=search,
            filter_columns_config=USER_FILTER_OPTIONS_CONFIG,
        )

        if not permissions.is_super_admin:
            df_data = _filter_manageable_users(df_data, permissions)
            total_after_filter = len(df_data)
            meta = PaginationMeta(
                page=meta.page,
                page_size=meta.page_size,
                total_rows=total_after_filter,
                total_pages=(
                    (total_after_filter + (meta.page_size or 1) - 1) // (meta.page_size or 1)
                    if meta.page_size else 1
                ),
                cache_hit=meta.cache_hit,
                profiling=meta.profiling,
            )

        users_json = df_to_json(df_data)

        users = []
        for user_dict in users_json:
            try:
                users.append(build_user_access_record(user_dict))
            except Exception as e:
                logger.error(f"Erro ao converter usuario {user_dict.get('cpf')}: {e}")
                raise

        if filter_options is not None:
            from src.utils.secretaria_access import get_allowed_secretaria_options

            allowed_values = get_allowed_secretaria_options(
                permissions.is_super_admin, permissions.secretarias_acesso
            )
            filter_options.secretarias_acesso_list = [
                FilterOption(id=value, label=SECRETARIA_LABELS.get(value, value))
                for value in allowed_values
            ]

        return users, meta, filter_options


class UpsertUserUseCase:
    def __init__(self, repository: IAdminRepository):
        self._repo = repository

    async def execute(
        self,
        permissions: CurrentUserPermissionsV2,
        cpf: str,
        request: UpsertUserRequest,
        user_token: str | None = None,
    ) -> UserAccessRecord:
        require_admin(permissions)

        if len(cpf) != 11 or not cpf.isdigit():
            raise ValidationError("CPF deve conter exatamente 11 digitos")

        governance_df, _, _ = await self._repo.fetch_governance_df()
        existing_user = governance_df.filter(pl.col("cpf") == cpf)
        user_exists = not existing_user.is_empty()

        if user_exists:
            existing_row = existing_user.row(0, named=True)
            is_target_super_admin = bool(existing_row.get("is_super_admin", False))
            is_target_admin = bool(existing_row.get("is_admin", False))

            if is_target_super_admin:
                raise ForbiddenError("Super admins nao podem ser editados")

            if is_target_admin and not permissions.is_super_admin:
                raise ForbiddenError("Admins nao podem editar outros admins")

            if not permissions.is_super_admin:
                admin_secretarias = set(permissions.secretarias_acesso or [])
                target_secretarias = set(existing_row.get("secretarias_acesso") or [])

                if not target_secretarias.issubset(admin_secretarias):
                    raise ForbiddenError(
                        f"Voce nao pode editar usuarios de outras secretarias. Voce tem acesso apenas a {sorted(admin_secretarias)}.",
                    )

        if cpf == permissions.cpf:
            raise ForbiddenError("Voce nao pode editar suas proprias permissoes")

        if request.is_super_admin and not permissions.is_super_admin:
            raise ForbiddenError("Apenas super admins podem criar ou promover outros super admins")

        if request.is_super_admin:
            raise ForbiddenError("Criacao de super admins nao e permitida via interface")

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

        is_new = not user_exists
        permission_value = calculate_permission(request.is_admin, request.is_super_admin)

        fields: dict[str, Any] = {}
        if request.email is not None:
            fields["email"] = request.email
        if request.nome is not None:
            fields["nome"] = request.nome
        if request.ocupacao is not None:
            fields["ocupacao"] = request.ocupacao
        if request.secretaria is not None:
            fields["secretaria"] = request.secretaria
        if request.secretarias_acesso is not None:
            fields["secretarias_acesso"] = request.secretarias_acesso
        if request.notes is not None:
            fields["notes"] = request.notes

        is_full_update = (
            request.email is not None or request.nome is not None
            or request.ocupacao is not None or request.secretaria is not None
            or request.secretarias_acesso is not None
            or request.id_cras_list is not None or request.id_escola_list is not None
        )

        if is_full_update:
            fields["is_admin"] = request.is_admin
            fields["is_super_admin"] = request.is_super_admin
            fields["permission"] = permission_value

        fields["active"] = request.active

        id_lists: dict[str, list[IdWithName] | None] = {
            "id_cras_list": request.id_cras_list,
            "id_escola_list": request.id_escola_list,
            "id_cre_list": request.id_cre_list,
            "id_ap_list": request.id_ap_list,
            "id_cas_list": request.id_cas_list,
            "id_clinica_familia_list": request.id_clinica_familia_list,
            "id_equipe_familia_list": request.id_equipe_familia_list,
        }

        if is_new:
            await self._repo.insert_user(cpf=cpf, fields=fields, id_lists=id_lists, created_by=permissions.cpf)
        else:
            await self._repo.update_user(cpf=cpf, fields=fields, id_lists=id_lists, updated_by=permissions.cpf)

        row_dict = await self._repo.fetch_user_record(cpf, user_token=user_token)

        if row_dict is None:
            raise RuntimeError(
                f"Usuario {cpf} salvo, mas nao encontrado no cache renovado"
            )

        return build_user_access_record(row_dict)


class DeleteUserUseCase:
    def __init__(self, repository: IAdminRepository):
        self._repo = repository

    async def execute(
        self,
        permissions: CurrentUserPermissionsV2,
        cpf: str,
        user_token: str | None = None,
    ) -> None:
        require_admin(permissions)

        governance_df, _, _ = await self._repo.fetch_governance_df()
        existing_user = governance_df.filter(pl.col("cpf") == cpf)

        if existing_user.is_empty():
            raise NotFoundError(f"Usuario {cpf} nao encontrado")

        existing_row = existing_user.row(0, named=True)
        is_target_super_admin = bool(existing_row.get("is_super_admin", False))
        is_target_admin = bool(existing_row.get("is_admin", False))

        if is_target_super_admin:
            raise ForbiddenError("Super admins nao podem ser deletados")

        if is_target_admin and not permissions.is_super_admin:
            raise ForbiddenError("Admins nao podem deletar outros admins")

        if not permissions.is_super_admin:
            admin_secretarias = set(permissions.secretarias_acesso or [])
            target_secretarias = set(existing_row.get("secretarias_acesso") or [])

            if not target_secretarias.issubset(admin_secretarias):
                raise ForbiddenError(
                    f"Voce nao pode deletar usuarios de outras secretarias. Voce tem acesso apenas a {sorted(admin_secretarias)}.",
                )

        if cpf == permissions.cpf:
            raise ForbiddenError("Voce nao pode deletar a si mesmo")

        await self._repo.soft_delete_user(cpf=cpf, updated_by=permissions.cpf)
