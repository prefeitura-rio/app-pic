from src.core.security.jwt import CurrentUserPermissionsV2
from src.pic.application.ports.admin_repository import IAdminRepository
from src.pic.application.use_cases.admin.id_utils import build_user_access_record
from src.pic.application.use_cases.admin.validation import require_admin
from src.pic.domain.models.admin import (
    UNIT_TYPE_REGISTRY,
    IdWithName,
    UserAccessRecord,
)
from src.utils.log import logger


class GetCurrentUserUseCase:
    """Builds the "my profile" record for the logged-in user.

    Goes through `fetch_user_record` (not the JWT hot-path `permissions`
    object directly) so unit IDs are resolved to real display names — with
    targeted PostgREST lookups only for this user's own ids. The hot path
    intentionally skips that join for speed and only needs raw IDs for RLS.
    """

    def __init__(self, repository: IAdminRepository):
        self._repo = repository

    async def execute(
        self,
        permissions: CurrentUserPermissionsV2,
        user_token: str | None = None,
        force_sync: bool = False,
    ) -> UserAccessRecord:
        from datetime import UTC, datetime

        # Self-heal safety net: retry any policy grant that failed to push
        # eagerly to the data-proxy at write time. Best-effort, never blocks
        # this request. When force_sync=True (fresh OAuth login), syncs ALL
        # policies regardless of synced_at status. See plan.md section 5.
        try:
            await self._repo.self_heal_policy_sync(permissions.cpf, force=force_sync)
        except Exception:
            logger.exception(f"Self-heal de policy sync falhou para {permissions.cpf}")

        row_dict = await self._repo.fetch_user_record(
            permissions.cpf, user_token=user_token
        )

        if row_dict is None:
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

        return build_user_access_record(row_dict)


def _group_ids_by_name(options: list[IdWithName]) -> list[IdWithName]:
    """v1 parity: ids sharing the same nome are joined with ","."""
    nome_to_ids: dict[str, list[str]] = {}
    for option in options:
        nome_to_ids.setdefault(option.nome, []).append(option.id)
    return [
        IdWithName(id=",".join(ids), nome=nome)
        for nome, ids in sorted(nome_to_ids.items())
    ]


class GetAvailableUnitIdsUseCase:
    """Available assignable IDs for one unit type (lazy, per dropdown).

    One grouped PostgREST query per type on dropdown open; RLS (user token)
    scopes the rows, so segmented admins naturally see only their own units.
    """

    def __init__(self, repository: IAdminRepository):
        self._repo = repository

    async def execute(
        self,
        permissions: CurrentUserPermissionsV2,
        unit_type: str,
        user_token: str | None = None,
        bypass_cache: bool = False,
    ) -> list[IdWithName]:
        require_admin(permissions)

        policy_unit_type, _ = UNIT_TYPE_REGISTRY[unit_type]

        options = await self._repo.fetch_unit_options(
            policy_unit_type,
            user_token=user_token,
            bypass_cache=bypass_cache,
        )
        return _group_ids_by_name(options)
