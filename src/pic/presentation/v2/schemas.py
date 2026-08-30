from pydantic import BaseModel

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


class FilterFieldOptionsResponse(BaseModel):
    field: str
    options: list[FilterOption]


class DashboardV2Response(BaseModel):
    data: Dashboard
    can_view_dashboard: bool = True


class GeospatialLayersResponse(BaseModel):
    data: list[GeospatialLayer]


class GeospatialFilterVocabularyResponse(GeospatialFilterOptions):
    pass
