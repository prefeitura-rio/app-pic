"""Schemas HTTP do endpoint de Acompanhamento (``/api/v2/monitoring/*``).

Espelham as saídas dos use cases (domain models), mantendo o contrato
explícito para o OpenAPI — mesmo padrão de ``v2/schemas.py``.
"""

from pydantic import BaseModel, Field

from src.pic.domain.models.monitoring import (
    MonitoringMeta,
    ProtocolOption,
    ProtocolPoint,
)


class MonitoringSeriesResponse(BaseModel):
    can_view_monitoring: bool = True
    protocolo: ProtocolOption | None = None
    meta: MonitoringMeta = Field(default_factory=MonitoringMeta)
    series: list[ProtocolPoint] = Field(default_factory=list)
