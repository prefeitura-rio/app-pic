from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.v1.queries import GEOSPATIAL_LAYERS_QUERY
from src.api.v1.schemas import (
    GeospatialFilterOptions,
    GeospatialFilters,
    GeospatialLayer,
    GeospatialPaginatedResponse,
)
from src.core.security.jwt import CurrentUserPermissions, verify_jwt
from src.utils.data_manager import DataManager
from src.utils.log import logger

router = APIRouter(dependencies=[Depends(verify_jwt)], tags=["Geospatial"])

# Configuração de filtros para camadas geoespaciais
GEOSPATIAL_FILTER_COLUMN_MAP = {
    "tipo_camada": "tipo_camada",
    "categoria": "categoria",
    "regional": "regional",
    "bairro": "bairro",
    "regiao_administrativa": "regiao_administrativa",
    "subprefeitura": "subprefeitura",
    "nome": "nome",
}

GEOSPATIAL_FILTER_OPTIONS_CONFIG = {
    "tipos_camada": {"column": "tipo_camada"},
    "categorias": {"column": "categoria"},
    "regionais": {"column": "regional"},
    "bairros": {"column": "bairro"},
    "regioes_administrativas": {"column": "regiao_administrativa"},
    "subprefeituras": {"column": "subprefeitura"},
    "nomes": {"column": "nome"},
}


@router.get(
    "/geospatial/layers",
    summary="Obter camadas geoespaciais para visualização em mapas",
    response_model=GeospatialPaginatedResponse[GeospatialLayer],
)
async def get_geospatial_layers(
    permissions: CurrentUserPermissions,
    filters: GeospatialFilters = Depends(),
    bypass_cache: bool = Query(False, description="Forçar refresh do cache"),
) -> Any:
    """
    Retorna camadas geoespaciais com suporte a filtros.

    A resposta inclui:
    - data: Lista de camadas geoespaciais
    - meta: Informações de paginação (sempre retorna tudo com page_size=-1)
    - filters: Opções de filtros dinâmicas baseadas nos dados filtrados atuais

    Inclui equipamentos públicos (escolas, CRAS, clínicas) e divisões
    administrativas (bairros, APs, CREs) com geometrias GeoJSON.

    As geometrias são convertidas de GEOGRAPHY (BigQuery) para GeoJSON
    usando ST_AsGeoJSON para compatibilidade com bibliotecas de mapas.

    Filtros em cascata: as opções de filtro são calculadas APÓS aplicar os
    filtros ativos, mostrando apenas as opções disponíveis.
    """
    import time

    endpoint_start = time.perf_counter()
    logger.info("=" * 80)
    logger.info("🗺️ GEOSPATIAL LAYERS ENDPOINT CALLED")
    logger.info("=" * 80)
    logger.info("⏱️ [TIMING] Geospatial layers endpoint started")

    query = GEOSPATIAL_LAYERS_QUERY

    # Log filtros ativos
    filters_dict = filters.model_dump(exclude_none=True)
    logger.info(f"📊 Filters received: {filters_dict}")
    logger.info(f"🔄 Bypass Cache: {bypass_cache}")
    logger.info(f"👤 User permissions: {permissions}")

    try:
        # Converter filtros de API para colunas do DataFrame
        column_filters = {}
        for filter_key, filter_value in filters_dict.items():
            if filter_key in GEOSPATIAL_FILTER_COLUMN_MAP:
                column_name = GEOSPATIAL_FILTER_COLUMN_MAP[filter_key]
                # Handle comma-separated values (multi-select from frontend)
                if isinstance(filter_value, str) and "," in filter_value:
                    filter_value = [
                        v.strip() for v in filter_value.split(",") if v.strip()
                    ]
                column_filters[column_name] = filter_value

        # Fetch data from BigQuery with filters (sempre retorna tudo, sem paginação)
        # NOTA: Não passamos user_permissions aqui porque dados geoespaciais são públicos
        # e não têm as colunas necessárias para filtros de governança (id_cras, id_escola, etc.)
        df_data, meta, filter_options = await DataManager.fetch_filter_paginate(
            query=query,
            filters_dict=column_filters,
            page=1,
            page_size=-1,  # Retornar todas as camadas (sem paginação)
            filter_columns_config=GEOSPATIAL_FILTER_OPTIONS_CONFIG,
            user_permissions=None,  # Geospatial data is public - no governance filters
            bypass_cache=bypass_cache,
        )

        # Converter DataFrame para JSON
        json_start = time.perf_counter()
        data_json = DataManager.df_to_json(df_data)
        json_time = time.perf_counter() - json_start

        # Construir resposta com filtros geoespaciais
        response_start = time.perf_counter()

        # Converter SmartFilterOptions (genérico) para GeospatialFilterOptions (específico)
        geospatial_filters = None
        if filter_options:
            logger.info(f"🔍 filter_options type: {type(filter_options)}")
            # filter_options é um SmartFilterOptions genérico, extrair apenas campos geoespaciais
            geospatial_filters = GeospatialFilterOptions(
                tipos_camada=getattr(filter_options, "tipos_camada", []),
                categorias=getattr(filter_options, "categorias", []),
                regionais=getattr(filter_options, "regionais", []),
                bairros=getattr(filter_options, "bairros", []),
                regioes_administrativas=getattr(
                    filter_options, "regioes_administrativas", []
                ),
                subprefeituras=getattr(filter_options, "subprefeituras", []),
                nomes=getattr(filter_options, "nomes", []),
            )
            logger.info(
                f"🔍 geospatial_filters created with {len(geospatial_filters.tipos_camada)} tipos_camada, {len(geospatial_filters.nomes)} nomes"
            )
        else:
            logger.warning("⚠️ filter_options is None!")

        response = GeospatialPaginatedResponse(
            data=data_json,
            meta=meta,
            filters=geospatial_filters,
        )
        response_time = time.perf_counter() - response_start

        total_endpoint_time = time.perf_counter() - endpoint_start
        logger.info(
            f"⏱️ [TIMING] Geospatial layers complete: "
            f"df_to_json={json_time:.3f}s, "
            f"response_build={response_time:.3f}s, "
            f"total_handler={total_endpoint_time:.3f}s, "
            f"layers_count={len(data_json)}, "
            f"active_filters={len(column_filters)}"
        )

        return response

    except Exception as e:
        import traceback

        logger.error(f"❌ Error fetching geospatial layers: {e}")
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e)) from e
