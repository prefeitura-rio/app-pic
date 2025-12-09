from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, List, Optional, Union

from src.core.security.jwt import verify_jwt, CurrentUserPermissions
from src.utils.log import logger
from src.api.v1.schemas import (
    Participante,
    ProtocoloDetalhes,
    PaginatedResponse,
    CommonFilters,
    PaginationParams,
)
from src.utils.data_manager import DataManager
from src.utils.data_manager_config import DataManagerConfig as config
from src.api.v1.queries import PARTICIPANTS_TABLE_QUERY

router = APIRouter(dependencies=[Depends(verify_jwt)], tags=["Participantes"])

# Configuração de filtros para participantes (definido no endpoint, não no DataManager)
PARTICIPANT_FILTER_COLUMN_MAP = {
    "bairro": "bairro",
    "cre": "id_cre",
    "ap": "id_ap",  # ATUALIZADO: AP substitui CAP
    "cas": "id_cas",
    "cras": "id_cras",
    "escola": "id_escola",
    "clinica": "id_clinica_familia",
    "safra": "cohort",
    "grupo": "grupo",
    "status": "status",
    "situacao": "situacao",
}

PARTICIPANT_FILTER_OPTIONS_CONFIG = {
    "bairros": {"column": "bairro"},
    "grupos": {"column": "grupo"},
    "cohorts": {"column": "cohort"},
    "status_list": {"column": "status"},
    "situacoes": {"column": "situacao"},
    "cres": {"column": "id_cre", "label_column": "nome_cre"},
    "aps": {"column": "id_ap", "label_column": "nome_ap"},  # ATUALIZADO: caps → aps, CAP → AP
    "cas_list": {"column": "id_cas", "label_column": "nome_cas"},
    "cras": {"column": "id_cras", "label_column": "nome_cras"},
    "escolas": {"column": "id_escola", "label_column": "nome_escola"},
    "clinicas": {
        "column": "id_clinica_familia",
        "label_column": "nome_clinica_familia",
    },
}


@router.get(
    "/participants",
    summary="Listar participantes com filtros e paginação",
    response_model=PaginatedResponse[Participante],
)
async def get_participants(
    permissions: CurrentUserPermissions,  # NOVO: Inject user permissions
    filters: CommonFilters = Depends(),
    pagination: PaginationParams = Depends(),
    bypass_cache: bool = Query(False, description="Forçar refresh do cache"),
) -> Any:
    """
    Retorna participantes com suporte a filtros e paginação.

    A resposta inclui:
    - data: Lista paginada de participantes
    - meta: Informações de paginação (página atual, total de páginas, etc.)
    - filters: Opções de filtros dinâmicas baseadas nos dados filtrados atuais

    As opções de filtro são calculadas APÓS aplicar os filtros, mostrando apenas
    as opções disponíveis considerando os filtros já ativos. Isso evita discrepâncias
    entre contadores e resultados reais.
    """
    query = PARTICIPANTS_TABLE_QUERY

    logger.info(
        f"Fetching participants - Page: {pagination.page}, Size: {pagination.page_size}"
    )
    logger.info(f"Filters: {filters.model_dump(exclude_none=True)}")
    logger.info(f"🔄 Bypass Cache: {bypass_cache}")

    try:
        # Converter filtros de API para colunas do DataFrame
        filters_dict = filters.model_dump(exclude_none=True)

        # Extrair search_term se existir
        search_term = filters_dict.pop("search", None)

        column_filters = {}
        for filter_key, filter_value in filters_dict.items():
            if filter_key in PARTICIPANT_FILTER_COLUMN_MAP:
                column_name = PARTICIPANT_FILTER_COLUMN_MAP[filter_key]
                column_filters[column_name] = filter_value

        # Pipeline completo: fetch -> governance -> filter -> search -> filter_options -> paginate
        # Se bypass_cache=True, força query no BigQuery para garantir dados frescos
        df_data, meta, filter_options = DataManager.fetch_filter_paginate(
            query=query,
            filters_dict=column_filters,
            page=pagination.page,
            page_size=pagination.page_size,
            filter_columns_config=PARTICIPANT_FILTER_OPTIONS_CONFIG,
            search_term=search_term,
            search_columns=["nome", "cpf"] if search_term else None,
            user_permissions=permissions,  # NOVO: Pass user permissions
            bypass_cache=bypass_cache,  # IMPORTANTE: Passa bypass_cache para forçar refresh
        )

        # OTIMIZAÇÃO: Converter DataFrame para JSON apenas aqui (última etapa)
        data_json = DataManager.df_to_json(df_data)

        return PaginatedResponse(
            data=data_json,
            meta=meta,
            filters=filter_options,
        )

    except Exception as e:
        logger.error(f"❌ Error fetching participants: {e}")
        raise HTTPException(status_code=500, detail=str(e))
