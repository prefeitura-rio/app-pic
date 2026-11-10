"""Schemas HTTP dos endpoints de Acompanhamento (``/api/v2/monitoring/*``).

Espelham as saídas dos use cases (domain models), mantendo o contrato
explícito para o OpenAPI — mesmo padrão de ``v2/schemas.py``.
"""

from pydantic import BaseModel, Field

from src.pic.domain.models.monitoring import (
    GroupPoint,
    MonitoringMeta,
    MonitoringOption,
    MotivoInativo,
    ProtocolOption,
    ProtocolPoint,
    ProtocolSummary,
)


class MonitoringFiltersResponse(BaseModel):
    grupos: list[MonitoringOption] = Field(default_factory=list)
    cohorts: list[MonitoringOption] = Field(default_factory=list)
    status: list[MonitoringOption] = Field(default_factory=list)
    protocolos: list[ProtocolOption] = Field(default_factory=list)
    secretarias: list[str] = Field(default_factory=list)


class MonitoringGroupResponse(BaseModel):
    can_view_monitoring: bool = True
    meta: MonitoringMeta = Field(default_factory=MonitoringMeta)
    series: list[GroupPoint] = Field(default_factory=list)
    motivos: list[MotivoInativo] = Field(default_factory=list)


class MonitoringSeriesResponse(BaseModel):
    can_view_monitoring: bool = True
    protocolo: ProtocolOption | None = None
    meta: MonitoringMeta = Field(default_factory=MonitoringMeta)
    series: list[ProtocolPoint] = Field(default_factory=list)


class MonitoringProtocolsResponse(BaseModel):
    can_view_monitoring: bool = True
    week_start: str | None = None
    snapshot_date: str | None = None
    protocols: list[ProtocolSummary] = Field(default_factory=list)
