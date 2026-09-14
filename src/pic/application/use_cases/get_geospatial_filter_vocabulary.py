from src.pic.application.ports.geospatial_repository import IGeospatialRepository
from src.pic.domain.models.geospatial import GeospatialFilterOptions


class GetGeospatialFilterVocabularyUseCase:
    def __init__(self, repository: IGeospatialRepository):
        self._repository = repository

    async def execute(
        self,
        user_token: str | None = None,
        bypass_cache: bool = False,
    ) -> GeospatialFilterOptions:
        return await self._repository.get_filter_vocabulary(
            user_token=user_token,
            bypass_cache=bypass_cache,
        )
