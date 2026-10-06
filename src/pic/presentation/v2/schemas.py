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
