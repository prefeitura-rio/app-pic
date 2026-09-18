import asyncio
from typing import Any

from src.pic.application.ports.disparos_repository import (
    DisparosRepository,
)
from src.pic.application.ports.participant_repository import (
    ParticipantRepository,
)
from src.pic.domain.errors import NotFoundError
from src.pic.domain.models.participante import Participante


class GetParticipantDetailUseCase:
    """Fetch one participant's detail plus the WhatsApp disparos.

    Both reads depend only on `id_membro_familia`, so they run concurrently
    (`asyncio.gather`); the disparos read is best-effort — `None` on
    data-proxy failure — and never fails the detail.
    """

    def __init__(
        self,
        repository: ParticipantRepository,
        disparos_repository: DisparosRepository,
    ):
        self._repository = repository
        self._disparos_repository = disparos_repository

    async def execute(
        self,
        id_membro_familia: str,
        permissions: Any = None,
        bypass_cache: bool = False,
        user_token: str | None = None,
    ) -> Participante:
        participante, disparos = await asyncio.gather(
            self._repository.get_participant_by_id(
                id_membro_familia=id_membro_familia,
                permissions=permissions,
                user_token=user_token,
            ),
            self._disparos_repository.get_disparos(
                id_membro_familia=id_membro_familia,
                user_token=user_token,
            ),
        )

        if participante is None:
            raise NotFoundError(
                f"Participante com id_membro_familia '{id_membro_familia}' nao encontrado"
            )

        if permissions and not permissions.is_super_admin:
            participante.latitude = None
            participante.longitude = None

        participante.disparos = disparos
        return participante
