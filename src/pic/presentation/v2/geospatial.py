from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.security.jwt import CurrentUserPermissions, verify_jwt
from src.pic.application.use_cases.get_geospatial_filter_vocabulary import (
    GetGeospatialFilterVocabularyUseCase,
)
from src.pic.application.use_cases.get_geospatial_layers import GetGeospatialLayersUseCase
from src.pic.domain.models.geospatial import GeospatialFilters
from src.pic.presentation.di import (
    get_geospatial_filter_vocabulary_use_case,
    get_geospatial_layers_use_case,
)
from src.pic.presentation.v2.schemas import (
    GeospatialFilterVocabularyResponse,
    GeospatialLayersResponse,
)
from src.utils.log import logger

router = APIRouter(dependencies=[Depends(verify_jwt)], tags=["Geospatial V2"])


@router.get(
    "/geospatial/layers",
    summary="Obter camadas geoespaciais para visualizacao em mapas (V2)",
    response_model=GeospatialLayersResponse,
)
async def get_geospatial_layers(
    permissions: CurrentUserPermissions,
    filters: GeospatialFilters = Depends(),
    bypass_cache: bool = Query(False, description="Forcar refresh do cache"),
    use_case: GetGeospatialLayersUseCase = Depends(get_geospatial_layers_use_case),
):
    try:
        result = await use_case.execute(filters=filters, bypass_cache=bypass_cache)
    except Exception as e:
        logger.error(f"Error fetching geospatial layers: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e

    return GeospatialLayersResponse(data=result.data)


@router.get(
    "/geospatial/filters",
    summary="Vocabulario de filtros geoespaciais disponiveis (V2)",
    response_model=GeospatialFilterVocabularyResponse,
)
async def get_geospatial_filters(
    bypass_cache: bool = Query(False, description="Forcar refresh do cache"),
    use_case: GetGeospatialFilterVocabularyUseCase = Depends(
        get_geospatial_filter_vocabulary_use_case
    ),
):
    return await use_case.execute(bypass_cache=bypass_cache)
