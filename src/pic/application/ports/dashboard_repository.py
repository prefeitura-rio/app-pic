from abc import ABC, abstractmethod

from src.pic.domain.models.dashboard import Dashboard


class IDashboardRepository(ABC):
    @abstractmethod
    async def get_dashboard_metrics(
        self,
        filters: dict[str, object],
        user_token: str | None = None,
        secretaria: str | None = None,
        bypass_cache: bool = False,
    ) -> Dashboard:
        ...
