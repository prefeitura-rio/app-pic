from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List

from src.core.security.jwt import verify_jwt
from src.config import env
from src.utils.bigquery import get_bigquery_result
from src.utils.log import logger

PROJECT_ID = env.BQ_PROJECT_ID
DATASET_ID = env.BQ_DATASET_ID

# router = APIRouter(dependencies=[Depends(verify_jwt)], prefix="/dash")
router = APIRouter(prefix="/dash", tags=["Dashboard"])


@router.get("/participants")
async def get_participantes() -> List[Dict[str, Any]]:
    query = f"""
    SELECT 
        *
    FROM `{PROJECT_ID}.{DATASET_ID}.endpoint_participante`
    LIMIT 10
    """

    logger.debug(f"Executing query: {query}")

    try:
        r = get_bigquery_result(query=query)
        return r
    except Exception as e:
        logger.error(f"Error fetching participants: {e}")
        raise HTTPException(status_code=500, detail=str(e))
