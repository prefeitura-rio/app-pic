import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Security
from fastapi.security import HTTPAuthorizationCredentials

from src.core.security.jwt import CurrentUserPermissionsV2, security, verify_jwt
from src.pic.application.use_cases.get_detalhes_regiao import (
    GetDetalhesRegiaoUseCase,
)
from src.pic.application.use_cases.get_geospatial_filter_options import (
    GetGeospatialFilterOptionsUseCase,
)
from src.pic.application.use_cases.get_geospatial_filter_vocabulary import (
    GetGeospatialFilterVocabularyUseCase,
)
from src.pic.application.use_cases.get_geospatial_layers import (
    GetGeospatialLayersUseCase,
)
from src.pic.application.use_cases.get_protocolos import GetProtocolosUseCase
from src.pic.application.use_cases.get_regularidade_por_camada import (
    GetRegularidadePorCamadaUseCase,
)
from src.pic.domain.models.geospatial import GeospatialFilters
from src.pic.infrastructure.repositories.geometrias_estaticas_repository import (
    fetch_geometria_estatica,
)
from src.pic.presentation.di import (
    get_detalhes_regiao_use_case,
    get_geospatial_filter_options_use_case,
    get_geospatial_filter_vocabulary_use_case,
    get_geospatial_layers_use_case,
    get_protocolos_use_case,
    get_regularidade_por_camada_use_case,
)
from src.pic.presentation.v2._helpers import data_proxy_user_token
from src.pic.presentation.v2.schemas import (
    BairrosGeoJSONResponse,
    GeospatialFilterFieldOptionsResponse,
    GeospatialFilterVocabularyResponse,
    GeospatialLayersResponse,
    ProtocoloOptionModel,
    ProtocolosResponse,
    RegiaoDetalhesResponse,
    RegiaoProtocoloMetricaModel,
    RegiaoRegularidadeGeoJSONResponse,
    RegiaoRegularidadeResumoModel,
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
    "/geospatial/bairros",
    summary="Limites oficiais de bairros (snapshot datario) em GeoJSON — POC aba Mapas",
    response_model=BairrosGeoJSONResponse,
)
async def get_bairros(
    permissions: CurrentUserPermissionsV2,
    bypass_cache: bool = Query(False, description="Forcar refresh do cache"),
):
    """Retorna os limites de bairros do Rio de Janeiro (fonte: datario/IPP).

    POC da visualização geográfica: 167 polígonos em WGS84, sem indicadores
    nem interação. Servidos do GeoJSON estático commitado
    (``bairros.json`` — fase 3g), sem consulta ao BigQuery em runtime.
    """
    try:
        features = fetch_geometria_estatica("bairro", bypass_cache=bypass_cache)
    except Exception as e:
        logger.error(f"Error fetching bairros (static): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e

    return BairrosGeoJSONResponse(features=features)


@router.get(
    "/geospatial/regularidade",
    summary="Regularidade agregada por camada territorial — escala red/green",
    response_model=RegiaoRegularidadeGeoJSONResponse,
)
async def get_regularidade_por_camada(
    permissions: CurrentUserPermissionsV2,
    camada: Literal["bairro", "ra", "cas", "cre", "ap"] = Query(
        ...,
        description=(
            "Camada territorial: 'bairro', 'ra' (Região Administrativa), "
            "'cas', 'cre' ou 'ap'"
        ),
    ),
    status: list[Literal["Ativo", "Inativo"]] | None = Query(
        None,
        description=(
            "Filtra por status do participante (pic_status=in) — multiselect, "
            "mesmo padrão da Visão Geral (ex.: status=Ativo)"
        ),
    ),
    cohortes: list[datetime.date] | None = Query(
        None,
        description=(
            "Meses de ingresso (pic_cohort=in) — multiselect de períodos de "
            "ingresso, mesmo padrão da Visão Geral (ex.: "
            "cohortes=2025-03-01&cohortes=2025-04-01)"
        ),
    ),
    protocolo_id: str | None = Query(
        None,
        description=(
            "Filtra por protocolo (FR-007): troca a fonte para a visão geral "
            "de protocolos e a métrica passa a ser a regularidade daquele "
            "protocolo (ex.: 'sms_vacinacao_pentavalente')"
        ),
    ),
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
    use_case: GetRegularidadePorCamadaUseCase = Depends(
        get_regularidade_por_camada_use_case
    ),
):
    """Retorna a geometria da camada com a taxa de regularidade por região.

    Mesma métrica do dashboard: participantes regulares (Regular + Atenção)
    sobre o total de participantes, agregados pelo PostgREST (tabela
    consolidado, RLS respeitada por usuário); a geometria vem dos GeoJSONs
    estáticos commitados (snapshot datario para bairro/ra; data.rio para
    cas/cre/ap). ``taxa_regularidade`` é None quando a região não tem
    participantes no escopo do usuário. Filtros opcionais (multiselect, mesmo
    padrão da Visão Geral): ``status`` (Ativo/Inativo) e ``cohortes`` (meses
    de ingresso). Sem ``status`` ou ``cohortes``, nenhum filtro é aplicado.
    """
    try:
        result = await use_case.execute(
            camada=camada,
            user_token=data_proxy_user_token(data_proxy_token, credentials.credentials),
            user_id=permissions.cpf if permissions else None,
            bypass_cache=bypass_cache,
            status=list(status) if status else None,
            cohortes=[c.isoformat() for c in cohortes] if cohortes else None,
            protocolo_id=protocolo_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Error fetching regularidade por camada: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e

    return RegiaoRegularidadeGeoJSONResponse(
        features=result.features,
        meta=result.meta,
    )


@router.get(
    "/geospatial/protocolos",
    summary="Vocabulário de protocolos para o filtro do mapa (V2)",
    response_model=ProtocolosResponse,
)
async def get_protocolos(
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
    bypass_cache: bool = Query(False, description="Forcar refresh do cache"),
    use_case: GetProtocolosUseCase = Depends(get_protocolos_use_case),
):
    """Retorna os protocolos distintos disponíveis (com RLS do usuário).

    Usado pelo seletor de protocolo da aba Mapas (FR-007): a seleção troca
    a regularidade geral pela regularidade daquele protocolo.
    """
    try:
        protocolos = await use_case.execute(
            user_token=data_proxy_user_token(data_proxy_token, credentials.credentials),
            user_id=permissions.cpf if permissions else None,
            bypass_cache=bypass_cache,
        )
    except Exception as e:
        logger.error(f"Error fetching protocolos: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e

    return ProtocolosResponse(
        protocolos=[
            ProtocoloOptionModel.model_validate(p.model_dump()) for p in protocolos
        ]
    )


@router.get(
    "/geospatial/regiao/detalhes",
    summary="Detalhes da região clicada: métrica geral + protocolos da região (V2)",
    response_model=RegiaoDetalhesResponse,
)
async def get_regiao_detalhes(
    permissions: CurrentUserPermissionsV2,
    camada: Literal["bairro", "ra", "cas", "cre", "ap"] = Query(
        ...,
        description=(
            "Camada territorial: 'bairro', 'ra' (Região Administrativa), "
            "'cas', 'cre' ou 'ap'"
        ),
    ),
    regiao: str = Query(
        ...,
        description=(
            "Identificador da região (o mesmo valor de properties.nome da "
            "feature clicada no mapa — ex.: 'Centro' para bairro, "
            "'Rio Comprido' para RA, '1ª CAS', 'AP 1.0')"
        ),
    ),
    status: list[Literal["Ativo", "Inativo"]] | None = Query(
        None,
        description=(
            "Filtra por status do participante (pic_status=in) — multiselect, "
            "mesmo padrão da Visão Geral (ex.: status=Ativo)"
        ),
    ),
    cohortes: list[datetime.date] | None = Query(
        None,
        description=(
            "Meses de ingresso (pic_cohort=in) — multiselect de períodos de "
            "ingresso, mesmo padrão da Visão Geral (ex.: "
            "cohortes=2025-03-01&cohortes=2025-04-01)"
        ),
    ),
    protocolo_id: str | None = Query(
        None,
        description=(
            "Quando informado, adiciona 'protocolo_geral' à resposta: a "
            "métrica do MESMO protocolo em todas as regiões (média geral) "
            "para o comparativo acima/abaixo da média (3k)"
        ),
    ),
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
    use_case: GetDetalhesRegiaoUseCase = Depends(get_detalhes_regiao_use_case),
):
    """Retorna o geral da região + a métrica de cada protocolo nela (3j/3k).

    Alimenta o card de detalhes da região clicada: sem protocolo selecionado
    o frontend exibe os cards por protocolo; com protocolo selecionado monta
    o comparativo com a média geral do protocolo (``protocolo_geral``).
    Filtros multiselect (``status``/``cohortes``) respeitados; RLS aplicada
    pelo data-proxy.
    """
    try:
        result = await use_case.execute(
            camada=camada,
            regiao=regiao,
            user_token=data_proxy_user_token(data_proxy_token, credentials.credentials),
            user_id=permissions.cpf if permissions else None,
            bypass_cache=bypass_cache,
            status=list(status) if status else None,
            cohortes=[c.isoformat() for c in cohortes] if cohortes else None,
            protocolo_id=protocolo_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Error fetching detalhes da região: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e

    return RegiaoDetalhesResponse(
        camada=result.camada,
        regiao=result.regiao,
        geral=(
            RegiaoRegularidadeResumoModel(
                **result.geral.model_dump()
            )
            if result.geral
            else None
        ),
        protocolo_geral=(
            RegiaoRegularidadeResumoModel(**result.protocolo_geral.model_dump())
            if result.protocolo_geral
            else None
        ),
        protocolos=[
            RegiaoProtocoloMetricaModel(**p.model_dump())
            for p in result.protocolos
        ],
    )


@router.get(
    "/geospatial/bairros-regularidade",
    summary="[deprecated] Regularidade por bairro — use /geospatial/regularidade?camada=bairro",
    response_model=RegiaoRegularidadeGeoJSONResponse,
    deprecated=True,
)
async def get_bairros_regularidade(
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
    bypass_cache: bool = Query(False, description="Forcar refresh do cache"),
    use_case: GetRegularidadePorCamadaUseCase = Depends(
        get_regularidade_por_camada_use_case
    ),
):
    """Alias legado da fase 2 — delegado a ``/geospatial/regularidade`` com ``camada=bairro``.

    Mantido para compatibilidade; o contrato de resposta é o genérico da
    camada (``properties.id`` no lugar de ``id_bairro``).
    """
    try:
        result = await use_case.execute(
            camada="bairro",
            user_token=data_proxy_user_token(data_proxy_token, credentials.credentials),
            user_id=permissions.cpf if permissions else None,
            bypass_cache=bypass_cache,
        )
    except Exception as e:
        logger.error(f"Error fetching bairros regularidade: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e

    return RegiaoRegularidadeGeoJSONResponse(
        features=result.features,
        meta=result.meta,
    )


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
