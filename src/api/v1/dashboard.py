from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Any

from src.core.security.jwt import verify_jwt
from src.config import env
from src.utils.log import logger
from src.api.v1.schemas import Dashboard, PaginatedResponse
from src.utils.data_manager import DataManager
from src.utils.data_manager_config import DataManagerConfig as config

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
        # Dashboard não tem filtros, apenas retorna tudo
        return DataManager.fetch_filter_paginate(
            query=query,
            filters_dict={},  # Sem filtros
            page=1,
            page_size=config.MAX_PAGE_SIZE,  # Retornar tudo
            filter_columns_config=None,  # Sem opções de filtro
        )

    except Exception as e:
        logger.error(f"Error fetching dashboard metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))
