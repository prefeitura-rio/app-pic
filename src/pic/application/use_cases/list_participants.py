from typing import Any

from src.pic.application.ports.participant_repository import (
    ParticipantRepository,
)
from src.pic.domain.models.filters import FilterCriteria
from src.pic.domain.models.pagination import (
    PaginationMeta,
    PaginationParams,
    SortParams,
)
from src.pic.domain.models.participante import ParticipanteListItem


class ParticipantListOutput:
    def __init__(
        self,
        data: list[ParticipanteListItem],
        meta: PaginationMeta,
    ):
        self.data = data
        self.meta = meta


class ListParticipantsUseCase:
    def __init__(self, repository: ParticipantRepository):
        self._repository = repository

    async def execute(
        self,
        filters: FilterCriteria,
        pagination: PaginationParams,
        sort: SortParams,
        permissions: Any = None,
        bypass_cache: bool = False,
        user_token: str | None = None,
    ) -> ParticipantListOutput:
        data, meta = await self._repository.list_participants(
            filters=filters,
            pagination=pagination,
            sort=sort,
            permissions=permissions,
            user_token=user_token,
            bypass_cache=bypass_cache,
        )
        return ParticipantListOutput(data=data, meta=meta)
