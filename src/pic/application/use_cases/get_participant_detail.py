import asyncio
from typing import Any

from src.pic.application.ports.busca_ativa_repository import (
    BuscaAtivaRepository,
)
from src.pic.application.ports.disparos_repository import (
    DisparosRepository,
)
from src.pic.application.ports.participant_repository import (
    ParticipantRepository,
)
from src.pic.domain.errors import NotFoundError
from src.pic.domain.models.participante import Participante


class GetParticipantDetailUseCase:
    """Fetch one participant's detail plus WhatsApp disparos and busca ativa.

    All reads depend only on `id_membro_familia`, so they run concurrently
    (`asyncio.gather`); the disparos/busca ativa reads are best-effort —
    `None` on data-proxy failure — and never fail the detail. Busca ativa is
    capped at `DETAIL_BUSCA_ATIVA_LIMIT` events (most recent first); the
    paginated route loads the rest.
    """

    DETAIL_BUSCA_ATIVA_LIMIT = 20

    def __init__(
        self,
        repository: ParticipantRepository,
        disparos_repository: DisparosRepository,
        busca_ativa_repository: BuscaAtivaRepository,
    ):
        self._repository = repository
        self._disparos_repository = disparos_repository
        self._busca_ativa_repository = busca_ativa_repository

    async def execute(
        self,
        id_membro_familia: str,
        permissions: Any = None,
        bypass_cache: bool = False,
        user_token: str | None = None,
    ) -> Participante:
        participante, disparos, busca_ativa = await asyncio.gather(
            self._repository.get_participant_by_id(
                id_membro_familia=id_membro_familia,
                permissions=permissions,
                user_token=user_token,
            ),
            self._disparos_repository.get_disparos(
                id_membro_familia=id_membro_familia,
                user_token=user_token,
            ),
            self._busca_ativa_repository.get_busca_ativa(
                id_membro_familia=id_membro_familia,
                user_token=user_token,
                offset=0,
                limit=self.DETAIL_BUSCA_ATIVA_LIMIT,
                permissions=permissions,
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
        participante.busca_ativa = busca_ativa
        return participante
