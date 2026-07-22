from pydantic import BaseModel

from src.pic.domain.models.dashboard import Dashboard
from src.pic.domain.models.filters import FilterVocabulary
from src.pic.domain.models.pagination import PaginationMeta
from src.pic.domain.models.participante import Participante, ParticipanteListItem


class ParticipantListResponse(BaseModel):
    meta: PaginationMeta
    data: list[ParticipanteListItem]


class ParticipantDetailResponse(BaseModel):
    data: Participante


class FilterVocabularyResponse(FilterVocabulary):
    pass


class DashboardV2Response(BaseModel):
    data: Dashboard
    can_view_dashboard: bool = True
