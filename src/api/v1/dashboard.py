from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List

from src.core.security.jwt import verify_jwt
from src.config import env
from src.utils.bigquery import get_bigquery_result
from src.utils.log import logger
from src.api.v1.schemas import Dashboard, PaginatedResponse

PROJECT_ID = env.BQ_PROJECT_ID
DATASET_ID = env.BQ_DATASET_ID

router = APIRouter(
    dependencies=[Depends(verify_jwt)],
)


@router.get("/", summary="Métricas do Dashboard", response_model=PaginatedResponse[Dashboard])
async def get_dashboard_metrics() -> Any:
    """
    Retorna métricas agregadas para o dashboard principal.
    """
    query = f"""
    SELECT 
        *
    FROM `{PROJECT_ID}.{DATASET_ID}.endpoint_dashboard`
    """
    logger.debug(f"Executing query: {query}")
    try:
        # Fetch all records for the dashboard (setting a high page_size)
        return get_bigquery_result(query=query, page_size=100000)
    except Exception as e:
        logger.error(f"Error fetching dashboard metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))
