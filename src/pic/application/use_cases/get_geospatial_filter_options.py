from src.pic.application.ports.geospatial_repository import IGeospatialRepository
from src.pic.domain.models.filters import FilterOption


class GetGeospatialFilterOptionsUseCase:
    """Return distinct values for a single geospatial filter field.

    Mirrors ``GetFilterOptionsUseCase`` for participants: one call per field,
    active filters are forwarded for cascade filtering so the returned options
    always reflect the current filter state.
    """

    def __init__(self, repository: IGeospatialRepository) -> None:
        self._repository = repository

    async def execute(
        self,
        field: str,
        column_filters: dict[str, object] | None = None,
        user_token: str | None = None,
        bypass_cache: bool = False,
    ) -> list[FilterOption]:
        return await self._repository.get_filter_options(
            field=field,
            column_filters=column_filters or {},
            user_token=user_token,
            bypass_cache=bypass_cache,
        )
