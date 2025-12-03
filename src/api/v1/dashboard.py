from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Any

from src.core.security.jwt import verify_jwt
from src.config import env
from src.utils.log import logger
from src.api.v1.schemas import Dashboard, PaginatedResponse
from src.utils.data_manager import DataManager

PROJECT_ID = env.BQ_PROJECT_ID
DATASET_ID = env.BQ_DATASET_ID

router = APIRouter(
    dependencies=[Depends(verify_jwt)],
)


@router.get(
    "/", summary="Métricas do Dashboard", response_model=PaginatedResponse[Dashboard]
)
async def get_dashboard_metrics() -> Any:
    """
    Retorna métricas agregadas para o dashboard principal.
    Os dados são obtidos da tabela pré-processada endpoint_dashboard.
    """

    query = f"""
    SELECT 
        *
    FROM `{PROJECT_ID}.{DATASET_ID}.endpoint_dashboard`
    """
    logger.debug(f"Fetching cached data for dashboard: {query}")
    try:
        # Get DataFrame from Manager
        df = DataManager.get_dataset(query)
        logger.debug(f"Dashboard total rows: {len(df)}")

        if df.empty:
            return {
                "data": [],
                "meta": {
                    "page": 1,
                    "page_size": 1,
                    "total_rows": 0,
                    "total_pages": 0,
                    "cache_hit": True,
                    "profiling": {},
                },
                "filters": None,
            }

        return DataManager.paginate_data(
            df,
            page=1,
            page_size=len(df) if not df.empty else 1,
        )

    except Exception as e:
        logger.error(f"Error fetching dashboard metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))
