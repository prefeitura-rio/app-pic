"""Modelos de domínio do Acompanhamento semanal (fase temporal do Monitoramento).

Fonte: ``endpoint_participante_visao_geral_semanal_protocolos`` — agregada por
protocolo/semana, sem identidade de participante. A evolução é **líquida**:
marginais por semana do grupo definido pelos filtros (não há transição
individual).

Convenções:
- "regular" inclui atenção: ``regular_total = regular + atencao``.
- Percentuais com denominador zero são ``None`` (não 0).
"""

from pydantic import BaseModel, Field

# Pseudo-protocolo da regularidade geral: linhas ``nivel='geral'`` da tabela
# semanal (``protocolo_id``/``protocolo_secretaria`` = ``'geral'``) — o número
# geral consolidado (participante regular em todos os protocolos aplicáveis),
# diferente da soma de pares participante-protocolo.
NIVEL_GERAL = "geral"


class MonitoringFilters(BaseModel):
    """Filtros compartilhados do endpoint de Acompanhamento.

    ``regiao`` são os valores RAW da coluna da camada na tabela semanal
    (ex.: ``"3ª Rio Comprido"`` para RA) - o use case os resolve a partir
    dos valores exibidos no mapa pelos agregados do consolidado. Múltiplas
    regiões viram um OR (``in``) na coluna da camada.
    """

    grupo: list[str] | None = None
    cohort: list[str] | None = None
    status: list[str] | None = None
    has_bolsa_familia: bool | None = None
    camada: str | None = None
    regiao: list[str] | None = None


class ProtocolWeekRow(BaseModel):
    """Linha retornada pelo repositório (ainda não agregada por semana)."""

    week_start: str
    snapshot_date: str | None = None
    status: str
    protocolo_descricao: str | None = None
    protocolo_secretaria: str | None = None
    qtd: int = 0
    regular: int = 0
    atencao: int = 0
    nao_priorizado: int = 0
    irregular: int = 0
    outros: int = 0
    nao_aplica: int = 0


class MonitoringMeta(BaseModel):
    """Metadados da janela semanal.

    ``window_start`` é o início da **janela estável**: a primeira semana da
    sequência contínua mais recente (sem lacunas). Tudo antes disso tem
    buracos de apuração e fica fora da UI por decisão de produto.
    """

    latest_week_start: str | None = None
    latest_snapshot_date: str | None = None
    latest_is_partial: bool = False
    available_weeks: list[str] = Field(default_factory=list)
    missing_weeks: list[str] = Field(default_factory=list)
    window_start: str | None = None
    weeks_count: int = 0
    has_data: bool = False


class StatusSlice(BaseModel):
    """Métrica do protocolo dentro de um status (Ativo/Inativo)."""

    total: int = 0
    regular: int = 0
    atencao: int = 0
    regular_total: int = 0
    irregular: int = 0


class ProtocolPoint(BaseModel):
    week_start: str
    snapshot_date: str | None = None
    total: int = 0
    nao_aplica: int = 0
    regular: int = 0
    atencao: int = 0
    regular_total: int = 0
    nao_priorizado: int = 0
    irregular: int = 0
    outros: int = 0
    regular_pct: float | None = None
    irregular_pct: float | None = None
    by_status: dict[str, StatusSlice] = Field(default_factory=dict)


class ProtocolOption(BaseModel):
    id: str
    descricao: str | None = None
    secretaria: str | None = None


class MonitoringSeriesOutput(BaseModel):
    can_view_monitoring: bool = True
    protocolo: ProtocolOption | None = None
    meta: MonitoringMeta = Field(default_factory=MonitoringMeta)
    series: list[ProtocolPoint] = Field(default_factory=list)
