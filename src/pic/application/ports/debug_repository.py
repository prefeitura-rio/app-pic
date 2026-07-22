from abc import ABC, abstractmethod

from src.pic.domain.models.debug import DebugParticipantResponse


class IDebugRepository(ABC):
    @abstractmethod
    async def search_participant_debug(
        self,
        search_term: str,
        bypass_cache: bool = False,
    ) -> DebugParticipantResponse:
        ...
