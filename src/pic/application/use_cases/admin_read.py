from src.core.security.jwt import CurrentUserPermissions
from src.pic.application.ports.admin_repository import IAdminRepository
from src.pic.domain.models.admin import AvailableIds, UserAccessRecord
from src.pic.infrastructure.admin.id_utils import _extract_unique_ids
from src.pic.infrastructure.admin.validation import require_admin


class GetCurrentUserUseCase:
    def execute(self, permissions: CurrentUserPermissions) -> UserAccessRecord:
        from datetime import UTC, datetime

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


class GetAvailableIdsUseCase:
    def __init__(self, repository: IAdminRepository):
        self._repo = repository

    async def execute(
        self,
        permissions: CurrentUserPermissions,
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

        return AvailableIds(
            cras=permissions.id_cras_list or [],
            escolas=permissions.id_escola_list or [],
            cres=permissions.id_cre_list or [],
            aps=permissions.id_ap_list or [],
            cas=permissions.id_cas_list or [],
            clinicas=permissions.id_clinica_familia_list or [],
            equipes_familia=permissions.id_equipe_familia_list or [],
        )
