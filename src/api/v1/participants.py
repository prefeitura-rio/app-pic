from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, List, Optional, Union

from src.core.security.jwt import verify_jwt
from src.config import env
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

PROJECT_ID = env.BQ_PROJECT_ID
DATASET_ID = env.BQ_DATASET_ID

router = APIRouter(
    dependencies=[Depends(verify_jwt)],
)

# Configuração de filtros para participantes (definido no endpoint, não no DataManager)
PARTICIPANT_FILTER_COLUMN_MAP = {
    "bairro": "bairro",
    "cre": "id_cre",
    "cap": "id_cap",
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
    "caps": {"column": "id_cap", "label_column": "nome_cap"},
    "cas_list": {"column": "id_cas", "label_column": "nome_cas"},
    "cras": {"column": "id_cras", "label_column": "nome_cras"},
    "escolas": {"column": "id_escola", "label_column": "nome_escola"},
    "clinicas": {
        "column": "id_clinica_familia",
        "label_column": "nome_clinica_familia",
    },
}


@router.get(
    "/",
    summary="Listar participantes com filtros e paginação",
    response_model=PaginatedResponse[Participante],
)
async def get_participants(
    filters: CommonFilters = Depends(), pagination: PaginationParams = Depends()
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
    query = f"""
    SELECT
        *
    FROM `{PROJECT_ID}.{DATASET_ID}.endpoint_participante`
    ORDER BY nome ASC
    """

    logger.info(
        f"Fetching participants - Page: {pagination.page}, Size: {pagination.page_size}"
    )
    logger.debug(f"Filters: {filters.model_dump(exclude_none=True)}")

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

        # Pipeline completo: fetch -> filter -> search -> filter_options -> paginate
        df_data, meta, filter_options = DataManager.fetch_filter_paginate(
            query=query,
            filters_dict=column_filters,
            page=pagination.page,
            page_size=pagination.page_size,
            filter_columns_config=PARTICIPANT_FILTER_OPTIONS_CONFIG,
            search_term=search_term,
            search_columns=["nome", "cpf"] if search_term else None,
        )

        # OTIMIZAÇÃO: Converter DataFrame para JSON apenas aqui (última etapa)
        data_json = DataManager.df_to_json(df_data)

        return PaginatedResponse(
            data=data_json,
            meta=meta,
            filters=filter_options,
        )

    except Exception as e:
        logger.error(f"Error fetching participants: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{cpf}",
    summary="Detalhes do participante",
    response_model=PaginatedResponse[Participante],
)
async def get_participant_details(cpf: str) -> Any:
    """
    Busca detalhes de um participante específico pelo CPF.
    """
    # Sanitização básica do CPF (apenas números)
    cpf_clean = "".join(filter(str.isdigit, cpf))

    query = f"""
    SELECT
        *
    FROM `{PROJECT_ID}.{DATASET_ID}.endpoint_participante`
    ORDER BY cpf DESC
    """
    try:
        # Tentar filtrar por CPF ou cpf_particao
        filters_dict = {"cpf": cpf}

        df_data, meta, filter_options = DataManager.fetch_filter_paginate(
            query=query,
            filters_dict=filters_dict,
            page=1,
            page_size=1,
            filter_columns_config=None,
        )

        # Se não encontrou por CPF, tentar por cpf_particao
        if meta.total_rows == 0:
            try:
                filters_dict = {"cpf_particao": int(cpf_clean)}
                df_data, meta, filter_options = DataManager.fetch_filter_paginate(
                    query=query,
                    filters_dict=filters_dict,
                    page=1,
                    page_size=1,
                    filter_columns_config=None,
                )
            except ValueError:
                pass

        if meta.total_rows == 0:
            raise HTTPException(status_code=404, detail="Participante não encontrado")

        # OTIMIZAÇÃO: Converter DataFrame para JSON apenas aqui (última etapa)
        data_json = DataManager.df_to_json(df_data)

        return PaginatedResponse(
            data=data_json,
            meta=meta,
            filters=filter_options,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching participant details: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{cpf}/protocols",
    summary="Protocolos do participante",
    response_model=PaginatedResponse[ProtocoloDetalhes],
)
async def get_participant_protocols(cpf: str) -> Any:
    """
    Lista os protocolos de um participante específico.
    """
    cpf_clean = "".join(filter(str.isdigit, cpf))

    # This is a different table, so it needs its own dataset cache
    query = f"""
    SELECT
        *
    FROM `{PROJECT_ID}.{DATASET_ID}.endpoint_protocolo_detalhes`
    ORDER BY protocolo_secretaria, protocolo_id
    """
    logger.debug(f"Fetching cached data for protocols: {query}")
    try:
        # Tentar filtrar por cpf_particao primeiro, depois por cpf
        filters_dict = {}
        try:
            filters_dict = {"cpf_particao": int(cpf_clean)}
        except ValueError:
            filters_dict = {"cpf": cpf}

        df_data, meta, filter_options = DataManager.fetch_filter_paginate(
            query=query,
            filters_dict=filters_dict,
            page=1,
            page_size=config.MAX_PAGE_SIZE,  # Retornar tudo
            filter_columns_config=None,
        )

        # OTIMIZAÇÃO: Converter DataFrame para JSON apenas aqui (última etapa)
        data_json = DataManager.df_to_json(df_data)

        return PaginatedResponse(
            data=data_json,
            meta=meta,
            filters=filter_options,
        )

    except Exception as e:
        logger.error(f"Error fetching participant protocols: {e}")
        raise HTTPException(status_code=500, detail=str(e))
