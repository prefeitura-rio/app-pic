from fastapi import APIRouter, Depends, Header, HTTPException, Query, Security
from fastapi.security import HTTPAuthorizationCredentials

from src.core.security.jwt import CurrentUserPermissionsV2, security, verify_jwt
from src.pic.application.use_cases.get_geospatial_filter_options import (
    GetGeospatialFilterOptionsUseCase,
)
from src.pic.application.use_cases.get_geospatial_filter_vocabulary import (
    GetGeospatialFilterVocabularyUseCase,
)
from src.pic.application.use_cases.get_geospatial_layers import (
    GetGeospatialLayersUseCase,
)
from src.pic.domain.models.geospatial import GeospatialFilters
from src.pic.presentation.di import (
    get_geospatial_filter_options_use_case,
    get_geospatial_filter_vocabulary_use_case,
    get_geospatial_layers_use_case,
)
from src.pic.presentation.v2._helpers import data_proxy_user_token
from src.pic.presentation.v2.schemas import (
    GeospatialFilterFieldOptionsResponse,
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
    permissions: CurrentUserPermissionsV2,
    credentials: HTTPAuthorizationCredentials = Security(security),
    data_proxy_token: str | None = Header(
        None,
        alias="X-Access-Token",
        description=(
            "Access token (Keycloak) repassado ao data-proxy (PostgREST); "
            "sem ele, usa o id_token do Authorization"
        ),
    ),
    filters: GeospatialFilters = Depends(),
    bypass_cache: bool = Query(False, description="Forcar refresh do cache"),
    use_case: GetGeospatialLayersUseCase = Depends(get_geospatial_layers_use_case),
):
    try:
        result = await use_case.execute(
            filters=filters,
            user_token=data_proxy_user_token(data_proxy_token, credentials.credentials),
            bypass_cache=bypass_cache,
        )
    except Exception as e:
        logger.error(f"Error fetching geospatial layers: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e

    return GeospatialLayersResponse(data=result.data)


@router.get(
    "/geospatial/filter-options",
    summary="Opcoes de valores para um campo de filtro geoespacial (lazy, por campo)",
    response_model=GeospatialFilterFieldOptionsResponse,
)
async def get_geospatial_filter_options(
    credentials: HTTPAuthorizationCredentials = Security(security),
    data_proxy_token: str | None = Header(
        None,
        alias="X-Access-Token",
        description=(
            "Access token (Keycloak) repassado ao data-proxy (PostgREST); "
            "sem ele, usa o id_token do Authorization"
        ),
    ),
    field: str = Query(
        ...,
        description=(
            "Campo de filtro a consultar. Valores validos: "
            "tipos_camada, categorias, regionais, bairros, "
            "regioes_administrativas, subprefeituras, nomes"
        ),
    ),
    filters: GeospatialFilters = Depends(),
    bypass_cache: bool = Query(False, description="Forcar refresh do cache"),
    use_case: GetGeospatialFilterOptionsUseCase = Depends(
        get_geospatial_filter_options_use_case
    ),
):
    """Retorna valores distintos para um único campo de filtro geoespacial.

    Aplica filtros ativos em cascata (exceto o do próprio campo), para que
    as opções reflitam o estado atual dos filtros — mesmo comportamento
    da listagem de participantes.
    """
    try:
        options = await use_case.execute(
            field=field,
            filters=filters,
            user_token=data_proxy_user_token(data_proxy_token, credentials.credentials),
            bypass_cache=bypass_cache,
        )
    except Exception as e:
        logger.error(
            f"Error fetching geospatial filter options for {field!r}: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=str(e)) from e

    return GeospatialFilterFieldOptionsResponse(field=field, options=options)


@router.get(
    "/geospatial/filters",
    summary="Vocabulario completo de filtros geoespaciais (V2) — todos os campos de uma vez",
    response_model=GeospatialFilterVocabularyResponse,
    deprecated=True,
)
async def get_geospatial_filters(
    credentials: HTTPAuthorizationCredentials = Security(security),
    data_proxy_token: str | None = Header(
        None,
        alias="X-Access-Token",
        description=(
            "Access token (Keycloak) repassado ao data-proxy (PostgREST); "
            "sem ele, usa o id_token do Authorization"
        ),
    ),
    bypass_cache: bool = Query(False, description="Forcar refresh do cache"),
    use_case: GetGeospatialFilterVocabularyUseCase = Depends(
        get_geospatial_filter_vocabulary_use_case
    ),
):
    """Retorna o vocabulário completo de filtros geoespaciais de uma só vez.

    **Deprecated**: prefira ``GET /geospatial/filter-options?field=<campo>``
    (lazy, por campo) para reduzir o payload inicial.
    """
    return await use_case.execute(
        user_token=data_proxy_user_token(data_proxy_token, credentials.credentials),
        bypass_cache=bypass_cache,
    )
