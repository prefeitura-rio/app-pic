"""Port do repositório do Acompanhamento semanal (monitoring).

Fonte única: ``endpoint_participante_visao_geral_semanal_protocolos`` no
data-proxy (PostgREST), com RLS aplicada ANTES da agregação — o escopo de
unidades do usuário é respeitado em todas as consultas.

O repositório devolve linhas ainda não agregadas (por semana/status/
protocolo); a agregação em séries, percentuais e meta é do use case.
"""

from abc import ABC, abstractmethod

from src.pic.domain.models.monitoring import MonitoringFilters, ProtocolWeekRow


class IMonitoringRepository(ABC):
    @abstractmethod
    async def fetch_protocol_series(
        self,
        protocolo_id: str,
        filters: MonitoringFilters,
        user_token: str | None = None,
        user_id: str | None = None,
        bypass_cache: bool = False,
    ) -> list[ProtocolWeekRow]:
        """Série semanal de UM protocolo, uma linha por semana × status."""
