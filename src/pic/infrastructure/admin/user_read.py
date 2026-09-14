from datetime import UTC, datetime

from src.api.v1.queries import GOVERNANCE_TABLE_QUERY, PARTICIPANTS_TABLE_QUERY
from src.config import env
from src.core.security.jwt import CurrentUserPermissions
from src.core.security.permissions_models import IdWithName
from src.pic.domain.models.admin import AvailableIds, UserAccessRecord
from src.pic.infrastructure.admin.config import USER_FILTER_OPTIONS_CONFIG
from src.pic.infrastructure.admin.id_utils import _extract_unique_ids
from src.pic.infrastructure.admin.validation import (
    _filter_manageable_users,
    require_admin,
)
from src.utils.data_manager import DataManager
from src.utils.log import logger

PROJECT_ID = env.BQ_PROJECT_ID
DATASET_ID = env.BQ_DATASET_ID
TABLE_ID_DATA_ACCESS = env.BQ_TABLE_ID_DATA_ACCESS


async def get_current_user_info(permissions: CurrentUserPermissions) -> UserAccessRecord:
    return UserAccessRecord(
        cpf=permissions.cpf,
        email=permissions.email,
        is_admin=permissions.is_admin,
        is_super_admin=permissions.is_super_admin,
        permission=permissions.permission,
        id_cras_list=permissions.id_cras_list,
        id_escola_list=permissions.id_escola_list,
        id_cre_list=permissions.id_cre_list,
        id_ap_list=permissions.id_ap_list,
        id_cas_list=permissions.id_cas_list,
        id_clinica_familia_list=permissions.id_clinica_familia_list,
        secretaria_acesso=permissions.secretaria_acesso,
        active=permissions.active,
        notes=permissions.notes if hasattr(permissions, "notes") else None,
        created_by=permissions.cpf,
        created_at=datetime.now(UTC),
    )


async def get_available_ids_data(permissions: CurrentUserPermissions) -> AvailableIds:
    require_admin(permissions)

    if permissions.is_super_admin:
        df, _, _ = await DataManager.get_dataset(PARTICIPANTS_TABLE_QUERY)
        available = AvailableIds(
            cras=_extract_unique_ids(df, "id_cras", "nome_cras"),
            escolas=_extract_unique_ids(df, "id_escola", "nome_escola"),
            cres=_extract_unique_ids(df, "id_cre", "id_cre"),
            aps=_extract_unique_ids(df, "id_ap", "nome_ap"),
            cas=_extract_unique_ids(df, "id_cas", "nome_cas"),
            clinicas=_extract_unique_ids(df, "id_clinica_familia", "nome_clinica_familia"),
            equipes_familia=_extract_unique_ids(df, "id_equipe_familia", "nome_equipe_familia"),
        )
    else:
        available = AvailableIds(
            cras=permissions.id_cras_list or [],
            escolas=permissions.id_escola_list or [],
            cres=permissions.id_cre_list or [],
            aps=permissions.id_ap_list or [],
            cas=permissions.id_cas_list or [],
            clinicas=permissions.id_clinica_familia_list or [],
            equipes_familia=permissions.id_equipe_familia_list or [],
        )

    return available


async def list_users_data(
    permissions: CurrentUserPermissions,
    page: int, page_size: int,
    active: bool | None,
    ocupacao: str | None,
    secretaria: str | None,
    permission: str | None,
    secretaria_acesso: str | None,
    search: str | None,
    bypass_cache: bool,
):
    require_admin(permissions)

    filters_dict = {}
    if active is not None:
        filters_dict["active"] = active
    if ocupacao:
        filters_dict["ocupacao"] = ocupacao
    if secretaria:
        filters_dict["secretaria"] = secretaria
    if permission:
        filters_dict["permission"] = permission
    if secretaria_acesso:
        filters_dict["secretaria_acesso"] = secretaria_acesso

    df_data, meta, filter_options = await DataManager.fetch_filter_paginate(
        query=GOVERNANCE_TABLE_QUERY,
        filters_dict=filters_dict,
        page=page,
        page_size=page_size,
        search_term=search,
        search_columns=["cpf", "nome"] if search else None,
        filter_columns_config=USER_FILTER_OPTIONS_CONFIG,
        user_permissions=None,
        bypass_cache=bypass_cache,
    )

    if not permissions.is_super_admin:
        df_data = _filter_manageable_users(df_data, permissions)
        total_after_filter = len(df_data)
        meta.total_rows = total_after_filter
        meta.total_pages = (
            (total_after_filter + meta.page_size - 1) // meta.page_size
            if meta.page_size else 1
        )

    users_json = DataManager.df_to_json(df_data)

    users = []
    for user_dict in users_json:
        try:
            for id_type in [
                "id_cras", "id_escola", "id_cre", "id_ap",
                "id_cas", "id_clinica_familia", "id_equipe_familia",
            ]:
                list_key = f"{id_type}_list"
                if list_key in user_dict and user_dict[list_key]:
                    user_dict[list_key] = [
                        IdWithName(**item) if isinstance(item, dict) else item
                        for item in user_dict[list_key]
                    ]
            users.append(UserAccessRecord(**user_dict))
        except Exception as e:
            logger.error(f"Erro ao converter usuario {user_dict.get('cpf')}: {e}")
            raise

    if filter_options and hasattr(filter_options, "secretaria_acesso_list"):
        from src.utils.secretaria_access import get_allowed_secretaria_options
        allowed_values = get_allowed_secretaria_options(
            permissions.is_super_admin, permissions.secretaria_acesso
        )
        filter_options.secretaria_acesso_list = [
            opt for opt in filter_options.secretaria_acesso_list
            if opt.id in allowed_values
        ]

    return users, meta, filter_options
