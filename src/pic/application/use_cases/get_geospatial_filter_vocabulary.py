from src.pic.application.ports.geospatial_repository import IGeospatialRepository
from src.pic.domain.models.geospatial import GeospatialFilterOptions


class GetGeospatialFilterVocabularyUseCase:
    def __init__(self, repository: IGeospatialRepository):
        self._repository = repository

    async def execute(
        self,
        bypass_cache: bool = False,
    ) -> GeospatialFilterOptions:
        return await self._repository.get_filter_vocabulary(
            bypass_cache=bypass_cache,
        )
