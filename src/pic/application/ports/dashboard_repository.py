from abc import ABC, abstractmethod
from typing import Any

from src.pic.domain.models.dashboard import Dashboard


class IDashboardRepository(ABC):
    @abstractmethod
    async def get_dashboard_metrics(
        self,
        filters: dict[str, object],
        permissions: Any = None,
        secretaria: str | None = None,
        bypass_cache: bool = False,
    ) -> Dashboard:
        ...
