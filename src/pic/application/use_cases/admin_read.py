import polars as pl

from src.core.security.jwt import CurrentUserPermissionsV2
from src.pic.application.ports.admin_repository import IAdminRepository
from src.pic.domain.models.admin import AvailableIds, UserAccessRecord
from src.pic.infrastructure.admin.id_utils import (
    _extract_unique_ids,
    build_user_access_record,
)
from src.pic.infrastructure.admin.validation import require_admin
from src.utils.data_manager import DataManager


class GetCurrentUserUseCase:
    """Builds the "my profile" record for the logged-in user.

    Goes through `fetch_governance_df` (not the JWT hot-path `permissions`
    object directly) so unit IDs are resolved to real display names via the
    participants catalog - the hot path intentionally skips that join for
    speed and only needs raw IDs for RLS filtering.
    """

    def __init__(self, repository: IAdminRepository):
        self._repo = repository

    async def execute(self, permissions: CurrentUserPermissionsV2) -> UserAccessRecord:
        from datetime import UTC, datetime

        governance_df, _, _ = await self._repo.fetch_governance_df()
        user_row = governance_df.filter(pl.col("cpf") == permissions.cpf) if not governance_df.is_empty() else governance_df

        if user_row.is_empty():
            # Shouldn't normally happen (permissions were just loaded from the
            # same users table), but fall back to the hot-path data so the
            # request doesn't fail outright.
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
                id_equipe_familia_list=permissions.id_equipe_familia_list,
                secretarias_acesso=permissions.secretarias_acesso,
                active=permissions.active,
                notes=permissions.notes,
                created_by=permissions.cpf,
                created_at=datetime.now(UTC),
            )

        row_dict = DataManager.df_to_json(user_row)[0]
        return build_user_access_record(row_dict)


class GetAvailableIdsUseCase:
    def __init__(self, repository: IAdminRepository):
        self._repo = repository

    async def execute(
        self,
        permissions: CurrentUserPermissionsV2,
        bypass_cache: bool = False,
    ) -> AvailableIds:
        require_admin(permissions)

        if permissions.is_super_admin:
            df, _, _ = await self._repo.fetch_participants_df(bypass_cache=bypass_cache)
            return AvailableIds(
                cras=_extract_unique_ids(df, "id_cras", "nome_cras"),
                escolas=_extract_unique_ids(df, "id_escola", "nome_escola"),
                cres=_extract_unique_ids(df, "id_cre", "id_cre"),
                aps=_extract_unique_ids(df, "id_ap", "nome_ap"),
                cas=_extract_unique_ids(df, "id_cas", "nome_cas"),
                clinicas=_extract_unique_ids(df, "id_clinica_familia", "nome_clinica_familia"),
                equipes_familia=_extract_unique_ids(df, "id_equipe_familia", "nome_equipe_familia"),
            )

        # Admin segmentado: retorna apenas os próprios IDs. Usa fetch_governance_df
        # (não o objeto `permissions` do hot-path) para resolver nomes reais via
        # catálogo de participantes - o hot-path só tem nome == id (fallback rápido).
        governance_df, _, _ = await self._repo.fetch_governance_df(bypass_cache=bypass_cache)
        user_row = (
            governance_df.filter(pl.col("cpf") == permissions.cpf)
            if not governance_df.is_empty()
            else governance_df
        )

        if user_row.is_empty():
            # Não deveria ocorrer (permissions acabaram de ser carregadas da
            # mesma tabela), mas evita falhar a requisição usando o hot-path.
            return AvailableIds(
                cras=permissions.id_cras_list or [],
                escolas=permissions.id_escola_list or [],
                cres=permissions.id_cre_list or [],
                aps=permissions.id_ap_list or [],
                cas=permissions.id_cas_list or [],
                clinicas=permissions.id_clinica_familia_list or [],
                equipes_familia=permissions.id_equipe_familia_list or [],
            )

        row_dict = DataManager.df_to_json(user_row)[0]
        user_record = build_user_access_record(row_dict)
        return AvailableIds(
            cras=user_record.id_cras_list or [],
            escolas=user_record.id_escola_list or [],
            cres=user_record.id_cre_list or [],
            aps=user_record.id_ap_list or [],
            cas=user_record.id_cas_list or [],
            clinicas=user_record.id_clinica_familia_list or [],
            equipes_familia=user_record.id_equipe_familia_list or [],
        )
