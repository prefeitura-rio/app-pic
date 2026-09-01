from abc import ABC, abstractmethod

from src.pic.domain.models.filters import FilterOption
from src.pic.domain.models.geospatial import GeospatialFilterOptions, GeospatialLayer


class IGeospatialRepository(ABC):
    @abstractmethod
    async def fetch_layers(
        self,
        column_filters: dict[str, object],
        user_token: str | None = None,
        bypass_cache: bool = False,
    ) -> list[GeospatialLayer]:
        ...

    @abstractmethod
    async def get_filter_options(
        self,
        field: str,
        column_filters: dict[str, object] | None = None,
        user_token: str | None = None,
        bypass_cache: bool = False,
    ) -> list[FilterOption]:
        """Return distinct non-null values for *field* (lazy, per-field vocab)."""
        ...

    @abstractmethod
    async def get_filter_vocabulary(
        self,
        user_token: str | None = None,
        bypass_cache: bool = False,
    ) -> GeospatialFilterOptions:
        """Return the full filter vocabulary (all fields, backward compat)."""
        ...
