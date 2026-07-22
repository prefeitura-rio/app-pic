from abc import ABC, abstractmethod

from src.pic.domain.models.geospatial import GeospatialFilterOptions, GeospatialLayer


class IGeospatialRepository(ABC):
    @abstractmethod
    async def fetch_layers(
        self,
        column_filters: dict[str, object],
        bypass_cache: bool = False,
    ) -> list[GeospatialLayer]:
        ...

    @abstractmethod
    async def get_filter_vocabulary(
        self,
        bypass_cache: bool = False,
    ) -> GeospatialFilterOptions:
        ...
