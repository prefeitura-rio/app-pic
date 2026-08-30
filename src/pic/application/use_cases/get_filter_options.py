from typing import Any

from src.pic.application.ports.participant_read_repository import (
    ParticipantRepository,
)
from src.pic.domain.models.filters import FilterCriteria, FilterOption


class GetFilterOptionsUseCase:
    def __init__(self, repository: ParticipantRepository):
        self._repository = repository

    async def execute(
        self,
        field: str,
        filters: FilterCriteria,
        permissions: Any = None,
        user_token: str | None = None,
        bypass_cache: bool = False,
    ) -> list[FilterOption]:
        return await self._repository.get_filter_options(
            field=field,
            filters=filters,
            permissions=permissions,
            user_token=user_token,
            bypass_cache=bypass_cache,
        )
