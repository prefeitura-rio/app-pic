from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Any, Optional

from src.core.security.jwt import verify_jwt
from src.config import env
from src.utils.log import logger
from src.api.v1.schemas import (
    FiltroEquipamento,
    FiltroRegional,
    PaginatedResponse,
)
from src.utils.data_manager import DataManager

PROJECT_ID = env.BQ_PROJECT_ID
DATASET_ID = env.BQ_DATASET_ID

router = APIRouter(
    dependencies=[Depends(verify_jwt)],
)




@router.get(
    "/equipments",
    summary="Filtros de Equipamentos",
    response_model=PaginatedResponse[FiltroEquipamento],
)
async def get_equipment_filters(
    tipo: Optional[str] = Query(
        None, description="Filtrar por tipo (ESCOLA, CLINICA_FAMILIA, CRAS)"
    )
) -> Any:
    """
    Retorna lista de equipamentos para filtros.
    """
    # Note: This query is different from the main participant one, so it gets its own cache entry.
    # We remove the WHERE clause from SQL to maximize cache hit ratio and filter in Python if needed,
    # OR we keep it if the dataset is massive. Given it's a filter table, it's likely small.
    # Let's fetch all and filter in Python for consistency with the new architecture.

    query = f"""
    SELECT 
        *
    FROM `{PROJECT_ID}.{DATASET_ID}.endpoint_filtros_equipamentos`
    ORDER BY nome
    """
    logger.debug(f"Fetching cached data for equipments: {query}")
    try:
        df = DataManager.get_dataset(query)

        # Apply Filter in Python
        if tipo and not df.empty and "tipo" in df.columns:
            df = df[df["tipo"] == tipo]

        return DataManager.paginate_data(df, page=1, page_size=10000)

    except Exception as e:
        logger.error(f"Error fetching equipment filters: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/regionals",
    summary="Filtros Regionais",
    response_model=PaginatedResponse[FiltroRegional],
)
async def get_regional_filters(
    tipo: Optional[str] = Query(None, description="Filtrar por tipo (CRE, CAP, CAS)")
) -> Any:
    """
    Retorna lista de regionais para filtros.
    """
    query = f"""
    SELECT 
        *
    FROM `{PROJECT_ID}.{DATASET_ID}.endpoint_filtros_regionais`
    ORDER BY nome
    """
    logger.debug(f"Fetching cached data for regionals: {query}")
    try:
        df = DataManager.get_dataset(query)

        # Apply Filter in Python
        if tipo and not df.empty and "tipo" in df.columns:
            df = df[df["tipo"] == tipo]

        return DataManager.paginate_data(df, page=1, page_size=10000)

    except Exception as e:
        logger.error(f"Error fetching regional filters: {e}")
        raise HTTPException(status_code=500, detail=str(e))
