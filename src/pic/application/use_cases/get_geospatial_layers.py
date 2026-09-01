from src.pic.application.ports.geospatial_repository import IGeospatialRepository
from src.pic.domain.models.geospatial import GeospatialFilters, GeospatialLayer
from src.pic.infrastructure.geospatial.config import GEOSPATIAL_FILTER_COLUMN_MAP


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
        filters_dict = filters.model_dump(exclude_none=True)

        column_filters: dict[str, object] = {}
        for filter_key, filter_value in filters_dict.items():
            if filter_key in GEOSPATIAL_FILTER_COLUMN_MAP:
                column_name = GEOSPATIAL_FILTER_COLUMN_MAP[filter_key]
                if isinstance(filter_value, str) and "," in filter_value:
                    filter_value = [
                        v.strip() for v in filter_value.split(",") if v.strip()
                    ]
                column_filters[column_name] = filter_value

        data = await self._repository.fetch_layers(
            column_filters=column_filters,
            user_token=user_token,
            bypass_cache=bypass_cache,
        )

        return GeospatialLayerOutput(data=data)
