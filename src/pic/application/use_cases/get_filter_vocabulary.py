from typing import Any

from src.pic.application.ports.participant_repository import IParticipantRepository
from src.pic.domain.models.filters import FilterVocabulary


class GetFilterVocabularyUseCase:
    def __init__(self, repository: IParticipantRepository):
        self._repository = repository

    async def execute(
        self,
        permissions: Any = None,
        bypass_cache: bool = False,
    ) -> FilterVocabulary:
        return await self._repository.get_filter_vocabulary(
            permissions=permissions,
            bypass_cache=bypass_cache,
        )
