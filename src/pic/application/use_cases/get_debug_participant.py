from fastapi import HTTPException

from src.core.security.jwt import CurrentUserPermissions
from src.pic.application.ports.debug_repository import IDebugRepository
from src.pic.domain.models.debug import DebugParticipantResponse


def _require_super_admin(permissions: CurrentUserPermissions) -> None:
    if not permissions.is_super_admin:
        raise HTTPException(
            status_code=403,
            detail="Acesso negado: apenas super admins podem acessar dados de debug",
        )


class GetDebugParticipantUseCase:
    def __init__(self, repository: IDebugRepository):
        self._repository = repository

    async def execute(
        self,
        permissions: CurrentUserPermissions,
        search: str | None = None,
        bypass_cache: bool = False,
    ) -> DebugParticipantResponse:
        _require_super_admin(permissions)

        if not search or len(search.strip()) == 0:
            return DebugParticipantResponse(total_found=0, total_returned=0, data=[])

        search_term = search.strip()
        return await self._repository.search_participant_debug(
            search_term=search_term,
            bypass_cache=bypass_cache,
        )
