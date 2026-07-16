from typing import Any

from src.pic.application.ports.participant_repository import IParticipantRepository
from src.pic.domain.errors import NotFoundError
from src.pic.domain.models.participante import Participante


class GetParticipantDetailUseCase:
    def __init__(self, repository: IParticipantRepository):
        self._repository = repository

    async def execute(
        self,
        id_membro_familia: str,
        permissions: Any = None,
        bypass_cache: bool = False,
    ) -> Participante:
        participante = await self._repository.find_by_membro_familia(
            id_membro_familia=id_membro_familia,
            permissions=permissions,
            bypass_cache=bypass_cache,
        )

        if participante is None:
            raise NotFoundError(
                f"Participante com id_membro_familia '{id_membro_familia}' nao encontrado"
            )

        if permissions and not permissions.is_super_admin:
            participante.latitude = None
            participante.longitude = None

        return participante
