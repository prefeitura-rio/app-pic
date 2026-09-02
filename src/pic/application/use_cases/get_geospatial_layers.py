from src.pic.application.ports.geospatial_repository import IGeospatialRepository
from src.pic.domain.models.geospatial import (
    GeospatialFilters,
    GeospatialLayer,
    geospatial_filters_to_columns,
)


class GeospatialLayerOutput:
    def __init__(self, data: list[GeospatialLayer]):
        self.data = data


class GetGeospatialLayersUseCase:
    def __init__(self, repository: IGeospatialRepository):
        self._repository = repository

    async def execute(
        self,
        filters: GeospatialFilters,
        user_token: str | None = None,
        bypass_cache: bool = False,
    ) -> GeospatialLayerOutput:
        data = await self._repository.fetch_layers(
            column_filters=geospatial_filters_to_columns(filters),
            user_token=user_token,
            bypass_cache=bypass_cache,
        )

        return GeospatialLayerOutput(data=data)
