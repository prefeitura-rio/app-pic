from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Any

from src.core.security.jwt import verify_jwt
from src.config import env
from src.utils.log import logger
from src.api.v1.schemas import Dashboard, PaginatedResponse, CommonFilters
from src.utils.data_manager import DataManager

PROJECT_ID = env.BQ_PROJECT_ID
DATASET_ID = env.BQ_DATASET_ID

router = APIRouter(
    dependencies=[Depends(verify_jwt)],
)


@router.get("/", summary="Métricas do Dashboard", response_model=PaginatedResponse[Dashboard])
async def get_dashboard_metrics(
    filters: CommonFilters = Depends()
) -> Any:
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
    logger.info(f"Dashboard filters received: bairro={filters.bairro}, cre={filters.cre}, cras={filters.cras}, safra={filters.safra}, grupo={filters.grupo}, status={filters.status}")

    try:
        # Get DataFrame from Manager
        df = DataManager.get_dataset(query)
        logger.debug(f"Dashboard total rows before filtering: {len(df)}")

        # Apply Filters using Manager
        # Note: The dashboard table should have the necessary columns for filtering
        # If filtering a pre-aggregated table, we need to re-fetch participant data
        # and re-aggregate, OR the dashboard table should be granular enough.
        # For now, we'll attempt to apply filters if columns exist.
        df = DataManager.apply_filters(df, filters)
        logger.debug(f"Dashboard total rows after filtering: {len(df)}")

        if df.empty:
             return {
                 "data": [],
                 "meta": {"page": 1, "page_size": 1, "total_rows": 0, "total_pages": 0, "cache_hit": True, "profiling": {}}
             }

        # Convert to records (effectively a single page of all data for the summary)
        # We can use paginate_data to wrap it correctly in the response model format
        return DataManager.paginate_data(df, page=1, page_size=len(df) if not df.empty else 1)

    except Exception as e:
        logger.error(f"Error fetching dashboard metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))
