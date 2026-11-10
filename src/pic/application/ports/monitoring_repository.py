"""Port do repositório do Acompanhamento semanal (monitoring).

Fonte única: ``endpoint_participante_visao_geral_semanal_protocolos`` no
data-proxy (PostgREST), com RLS aplicada ANTES da agregação — o escopo de
unidades do usuário é respeitado em todas as consultas.

O repositório devolve linhas ainda não agregadas (por semana/status/
protocolo); a agregação em séries, percentuais e meta é do use case.
"""

from abc import ABC, abstractmethod

from src.pic.domain.models.monitoring import (
    GroupWeekRow,
    MonitoringFilterOptions,
    MonitoringFilters,
    MotivoInativoRow,
    ProtocolWeekRow,
    ProtocolWeekSummaryRow,
)


class IMonitoringRepository(ABC):
    @abstractmethod
    async def fetch_filter_options(
        self,
        user_token: str | None = None,
        bypass_cache: bool = False,
    ) -> MonitoringFilterOptions:
        """Opções do card de filtros (grupos, cohorts, status, protocolos,
        secretarias) com contagens da última semana disponível.

        Cache global (independe do usuário) e TTL alto: são valores
        program-wide indicativos, não RLS-scoped (decisão do documento
        técnico, seção 5.5).
        """

    @abstractmethod
    async def fetch_group_series(
        self,
        filters: MonitoringFilters,
        user_token: str | None = None,
        user_id: str | None = None,
        bypass_cache: bool = False,
    ) -> list[GroupWeekRow]:
        """Série semanal do grupo (âncora ``PROTOCOLO_TOTAL``), uma linha por
        semana × status, ordenada por semana."""

    @abstractmethod
    async def fetch_motivos(
        self,
        latest_week: str,
        filters: MonitoringFilters,
        user_token: str | None = None,
        user_id: str | None = None,
        bypass_cache: bool = False,
    ) -> list[MotivoInativoRow]:
        """Motivos de inativação da semana mais recente com dados."""

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

    @abstractmethod
    async def fetch_protocols_summary(
        self,
        week_start: str,
        secretaria: str | None,
        filters: MonitoringFilters,
        user_token: str | None = None,
        user_id: str | None = None,
        bypass_cache: bool = False,
    ) -> list[ProtocolWeekSummaryRow]:
        """Uma linha por protocolo na semana (tabela "todos os protocolos")."""

    @abstractmethod
    async def fetch_latest_week(
        self,
        filters: MonitoringFilters,
        user_token: str | None = None,
        user_id: str | None = None,
        bypass_cache: bool = False,
    ) -> str | None:
        """Semana mais recente com dados para os filtros (âncora do grupo)."""
