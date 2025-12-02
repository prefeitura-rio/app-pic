from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, List, Optional, Union

from src.core.security.jwt import verify_jwt
from src.config import env
from src.utils.log import logger
from src.api.v1.schemas import Participante, ProtocoloDetalhes, PaginatedResponse, CommonFilters, PaginationParams
from src.utils.data_manager import DataManager

PROJECT_ID = env.BQ_PROJECT_ID
DATASET_ID = env.BQ_DATASET_ID

router = APIRouter(
    dependencies=[Depends(verify_jwt)],
)


@router.get(
    "/",
    summary="Listar participantes",
    response_model=PaginatedResponse[Participante],
)
async def get_participants(
    filters: CommonFilters = Depends(),
    pagination: PaginationParams = Depends()
) -> Any:
    """
    Busca lista de participantes com suporte a filtros e paginação.
    """
    query = f"""
    SELECT 
        *
    FROM `{PROJECT_ID}.{DATASET_ID}.endpoint_participante`
    ORDER BY cpf DESC
    """
    logger.debug(f"Fetching cached data for participants list: {query}")
    try:
        # Get DataFrame from Manager
        df = DataManager.get_dataset(query)
        
        # Apply Filters
        df = DataManager.apply_filters(df, filters)
        
        # Apply Pagination and Return Response Object
        return DataManager.paginate_data(df, pagination.page, pagination.page_size)

    except Exception as e:
        logger.error(f"Error fetching participants: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{cpf}", summary="Detalhes do participante", response_model=PaginatedResponse[Participante])
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
        if 'cpf' in df.columns:
             result = df[df['cpf'] == cpf]
             if result.empty and 'cpf_particao' in df.columns:
                 try:
                     result = df[df['cpf_particao'] == int(cpf_clean)]
                 except ValueError:
                     pass
        else:
             # Fallback (unlikely)
             result = df[0:0] 

        if result.empty:
            raise HTTPException(status_code=404, detail="Participante não encontrado")
            
        # Use DataManager to package the single result
        return DataManager.paginate_data(result, page=1, page_size=1)

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
        if 'cpf_particao' in df.columns:
             try:
                 df = df[df['cpf_particao'] == int(cpf_clean)]
             except ValueError:
                 df = df[0:0] # Empty
        elif 'cpf' in df.columns:
             df = df[df['cpf'] == cpf]
        
        # Use DataManager to package all results
        return DataManager.paginate_data(df, page=1, page_size=len(df) if not df.empty else 1)
        
    except Exception as e:
        logger.error(f"Error fetching participant protocols: {e}")
        raise HTTPException(status_code=500, detail=str(e))
