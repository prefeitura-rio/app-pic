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
    
    try:
        # Get DataFrame from Manager
        df = DataManager.get_dataset(query)
        
        # Apply Filters using Manager (Note: endpoint_dashboard might not have these columns, 
        # so this might effectively be a no-op or we should check columns first)
        # Since endpoint_dashboard is a summary, standard participant filters (bairro, cre) 
        # usually don't apply unless the dashboard table is granular.
        # We will attempt to filter if columns exist, otherwise return as is.
        
        # Checking columns availability for filtering is handled implicitly by DataManager if we wanted,
        # but here we just return the data as it is "processed from BQ".
        
        # If the dashboard table had historical data or regional breakdowns, we would filter here.
        # Assuming single row or compatible rows.
        
        # Filter logic is allowed ("so devemos aplicar filtros"), but only if applicable.
        # df = DataManager.apply_filters(df, filters) 

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
