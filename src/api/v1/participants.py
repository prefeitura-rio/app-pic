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

PROJECT_ID = env.BQ_PROJECT_ID
DATASET_ID = env.BQ_DATASET_ID

router = APIRouter(
    dependencies=[Depends(verify_jwt)],
)

# Configuração de filtros para participantes (definido no endpoint, não no DataManager)
PARTICIPANT_FILTER_COLUMN_MAP = {
    "bairro": "bairro",
    "cre": "id_cre",
    "cras": "id_cras",
    "escola": "id_escola",
    "clinica": "id_clinica_familia",
    "safra": "cohort",
    "grupo": "grupo",
    "status": "status",
}

PARTICIPANT_FILTER_OPTIONS_CONFIG = {
    "bairros": {"column": "bairro"},
    "grupos": {"column": "grupo"},
    "cohorts": {"column": "cohort"},
    "status_list": {"column": "status"},
    "cres": {"column": "id_cre"},
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
        # Get DataFrame from cache
        df = DataManager.get_dataset(query)

        # Converter filtros de API para colunas do DataFrame
        filters_dict = filters.model_dump(exclude_none=True)
        column_filters = {}
        for filter_key, filter_value in filters_dict.items():
            if filter_key in PARTICIPANT_FILTER_COLUMN_MAP:
                column_name = PARTICIPANT_FILTER_COLUMN_MAP[filter_key]
                column_filters[column_name] = filter_value

        # Apply filters using DataManager (genérico)
        df = DataManager.apply_filters(df, column_filters)

        logger.info(f"Total after filters: {len(df)} participants")

        # Paginate and return (includes dynamic filter options)
        return DataManager.paginate_data(
            df,
            pagination.page,
            pagination.page_size,
            filter_columns_config=PARTICIPANT_FILTER_OPTIONS_CONFIG,
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
        df = DataManager.get_dataset(query)

        # Filter by CPF partition/column
        if "cpf" in df.columns:
            result = df[df["cpf"] == cpf]
            if result.empty and "cpf_particao" in df.columns:
                try:
                    result = df[df["cpf_particao"] == int(cpf_clean)]
                except ValueError:
                    pass
        else:
            # Fallback (unlikely)
            result = df[0:0]

        if result.empty:
            raise HTTPException(status_code=404, detail="Participante não encontrado")

        # Use DataManager to package the single result (no filters needed for single record)
        return DataManager.paginate_data(
            result, page=1, page_size=1, filter_columns_config=None
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
        df = DataManager.get_dataset(query)

        # Filter by CPF
        if "cpf_particao" in df.columns:
            try:
                df = df[df["cpf_particao"] == int(cpf_clean)]
            except ValueError:
                df = df[0:0]  # Empty
        elif "cpf" in df.columns:
            df = df[df["cpf"] == cpf]

        # Use DataManager to package all results (no filters needed for protocols)
        return DataManager.paginate_data(
            df,
            page=1,
            page_size=len(df) if not df.empty else 1,
            filter_columns_config=None,
        )

    except Exception as e:
        logger.error(f"Error fetching participant protocols: {e}")
        raise HTTPException(status_code=500, detail=str(e))
