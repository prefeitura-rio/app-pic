from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List

from src.core.security.jwt import verify_jwt
from src.config import env
from src.utils.bigquery import get_bigquery_result
from src.utils.log import logger

PROJECT_ID = env.BQ_PROJECT_ID
DATASET_ID = env.BQ_DATASET_ID

router = APIRouter(
    dependencies=[Depends(verify_jwt)],
)

@router.get("/summary", summary="Resumo de Protocolos", response_model=List[Dict[str, Any]])
async def get_protocols_summary() -> List[Dict[str, Any]]:
    """
    Retorna resumo de violações de protocolos.
    """
    query = f"""
    SELECT 
        *
    FROM `{PROJECT_ID}.{DATASET_ID}.endpoint_protocolo_resumo`
    """
    logger.debug(f"Executing query: {query}")
    try:
        return get_bigquery_result(query=query)
    except Exception as e:
        logger.error(f"Error fetching protocols summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))
