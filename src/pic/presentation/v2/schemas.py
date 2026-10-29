from typing import Literal

from pydantic import BaseModel

from src.pic.domain.models.acordo_resultados import AcordoResultados
from src.pic.domain.models.admin import UserAccessRecord
from src.pic.domain.models.busca_ativa import BuscaAtivaEvento
from src.pic.domain.models.dashboard import Dashboard
from src.pic.domain.models.filters import FilterOption
from src.pic.domain.models.geospatial import GeospatialFilterOptions, GeospatialLayer
from src.pic.domain.models.pagination import PaginationMeta
from src.pic.domain.models.participante import Participante, ParticipanteListItem


class ParticipantListResponse(BaseModel):
    meta: PaginationMeta
    data: list[ParticipanteListItem]


class ParticipantDetailResponse(BaseModel):
    data: Participante


class BuscaAtivaPageMeta(BaseModel):
    offset: int
    limit: int
    has_more: bool


class BuscaAtivaPageResponse(BaseModel):
    data: list[BuscaAtivaEvento]
    meta: BuscaAtivaPageMeta


class AdminUsersResponse(BaseModel):
    meta: PaginationMeta
    data: list[UserAccessRecord]
    filters: object | None = None


class FilterFieldOptionsResponse(BaseModel):
    field: str
    options: list[FilterOption]


class DashboardV2Response(BaseModel):
    data: Dashboard
    can_view_dashboard: bool = True


class AcordoResultadosResponse(BaseModel):
    data: AcordoResultados
    can_view_acordo: bool = True


class GeospatialLayersResponse(BaseModel):
    data: list[GeospatialLayer]


class GeospatialFilterVocabularyResponse(GeospatialFilterOptions):
    pass


class GeospatialFilterFieldOptionsResponse(BaseModel):
    field: str
    options: list[FilterOption]


# ---------------------------------------------------------------------------
# POC — Visualização Geográfica (aba "Mapas"): limites oficiais de bairros
# ---------------------------------------------------------------------------


class BairroFeatureProperties(BaseModel):
    id_bairro: str
    nome: str
    nome_regiao_administrativa: str


class BairroFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    properties: BairroFeatureProperties
    geometry: dict


class BairrosGeoJSONResponse(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[BairroFeature]


class RegiaoRegularidadeProperties(BaseModel):
    """Propriedades genéricas de uma região de camada territorial.

    ``id`` é o identificador oficial da região (``id_bairro`` para bairro,
    ``id_regiao_administrativa`` para RA). ``nome_regiao_administrativa``
    existe apenas na camada "bairro" (vem da tabela datario de bairros).
    """

    id: str | None = None
    nome: str
    nome_regiao_administrativa: str | None = None
    total_participantes: int | None = None
    total_regulares: int | None = None
    total_irregulares: int | None = None
    taxa_regularidade: float | None = None


class RegiaoRegularidadeFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    properties: RegiaoRegularidadeProperties
    geometry: dict


class RegiaoRegularidadeMeta(BaseModel):
    camada: Literal["bairro", "ra", "cas", "cre", "ap"]
    total_regioes: int
    regioes_com_dados: int
    regioes_sem_dados: int
    agregados_sem_geometria: list[str]


class RegiaoRegularidadeGeoJSONResponse(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[RegiaoRegularidadeFeature]
    meta: RegiaoRegularidadeMeta


class ProtocoloOptionModel(BaseModel):
    protocolo_id: str
    protocolo_secretaria: str | None = None
    protocolo_descricao: str | None = None


class ProtocolosResponse(BaseModel):
    protocolos: list[ProtocoloOptionModel]


class RegiaoRegularidadeResumoModel(BaseModel):
    """Métrica de regularidade (geral ou de um protocolo) numa região."""

    total_participantes: int = 0
    total_regulares: int = 0
    total_irregulares: int = 0
    taxa_regularidade: float | None = None


class RegiaoProtocoloMetricaModel(RegiaoRegularidadeResumoModel):
    protocolo_id: str
    protocolo_secretaria: str | None = None
    protocolo_descricao: str | None = None


class RegiaoDetalhesResponse(BaseModel):
    camada: Literal["bairro", "ra", "cas", "cre", "ap"]
    regiao: str
    geral: RegiaoRegularidadeResumoModel | None = None
    protocolo_geral: RegiaoRegularidadeResumoModel | None = None
    protocolos: list[RegiaoProtocoloMetricaModel] = []
