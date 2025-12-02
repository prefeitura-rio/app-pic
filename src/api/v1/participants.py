from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, List, Optional, Union

from src.core.security.jwt import verify_jwt
from src.config import env
from src.utils.bigquery import get_bigquery_result
from src.utils.log import logger

PROJECT_ID = env.BQ_PROJECT_ID
DATASET_ID = env.BQ_DATASET_ID

router = APIRouter(
    # dependencies=[Depends(verify_jwt)],
)


@router.get(
    "/",
    summary="Listar participantes",
    response_model=Union[List[Dict[str, Any]], Dict[str, Any]],
)
async def get_participants(
    page: int = 1, page_size: int = env.GOOGLE_BIGQUERY_PAGE_SIZE
) -> Dict[str, Any]:
    """
    Busca lista de participantes.
    """
    query = f"""
    SELECT 
        *
    FROM `{PROJECT_ID}.{DATASET_ID}.endpoint_participante`
    ORDER BY cpf
    """
    logger.debug(f"Executing query: {query}")
    try:
        return get_bigquery_result(query=query, page_size=page_size, page=page)

    except Exception as e:
        logger.error(f"Error fetching participants: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{cpf}", summary="Detalhes do participante", response_model=Dict[str, Any])
async def get_participant_details(cpf: str) -> Dict[str, Any]:
    """
    Busca detalhes de um participante específico pelo CPF.
    """
    # Sanitização básica do CPF (apenas números)
    cpf_clean = "".join(filter(str.isdigit, cpf))

    query = f"""
    SELECT 
        *
    FROM `{PROJECT_ID}.{DATASET_ID}.endpoint_participante`
    WHERE cpf = '{cpf_clean}'
    LIMIT 1
    """
    logger.debug(f"Executing query: {query}")
    try:
        results = get_bigquery_result(query=query)
        if not results:
            raise HTTPException(status_code=404, detail="Participante não encontrado")
        return results[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching participant details: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{cpf}/protocols",
    summary="Protocolos do participante",
    response_model=List[Dict[str, Any]],
)
async def get_participant_protocols(cpf: str) -> List[Dict[str, Any]]:
    """
    Lista os protocolos de um participante específico.
    """
    cpf_clean = "".join(filter(str.isdigit, cpf))

    query = f"""
    SELECT 
        *
    FROM `{PROJECT_ID}.{DATASET_ID}.endpoint_protocolo_detalhes`
    WHERE cpf = '{cpf_clean}'
    ORDER BY protocolo_secretaria, protocolo_id
    """
    logger.debug(f"Executing query: {query}")
    try:
        return get_bigquery_result(query=query)
    except Exception as e:
        logger.error(f"Error fetching participant protocols: {e}")
        raise HTTPException(status_code=500, detail=str(e))
