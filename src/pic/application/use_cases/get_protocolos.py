"""Use case do vocabulário de protocolos para o filtro do mapa (fase 3e).

Retorna os protocolos distintos da ``endpoint_participante_visao_geral_protocolos``
(RLS aplicada pelo data-proxy) para popular o seletor de protocolo da aba
Mapas — FR-007 do fluxo: a seleção substitui a regularidade geral pela
regularidade daquele protocolo.
"""

from src.pic.application.ports.geospatial_repository import IGeospatialRepository
from src.pic.domain.models.geospatial import ProtocoloOption


class GetProtocolosUseCase:
    def __init__(self, repository: IGeospatialRepository):
        self._repository = repository

    async def execute(
        self,
        user_token: str | None = None,
        user_id: str | None = None,
        bypass_cache: bool = False,
    ) -> list[ProtocoloOption]:
        return await self._repository.fetch_protocolos(
            user_token=user_token,
            user_id=user_id,
            bypass_cache=bypass_cache,
        )
