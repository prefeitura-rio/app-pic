from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Any, Optional, List

from src.core.security.jwt import verify_jwt
from src.config import env
from src.utils.log import logger
from src.api.v1.schemas import (
    FiltroEquipamento,
    FiltroRegional,
    PaginatedResponse,
    FilterOptionsResponse,
    FiltroOpcao,
)
from src.utils.data_manager import DataManager

PROJECT_ID = env.BQ_PROJECT_ID
DATASET_ID = env.BQ_DATASET_ID

router = APIRouter(
    dependencies=[Depends(verify_jwt)],
)


@router.get(
    "/options",
    summary="Opções de Filtros Inteligentes",
    response_model=FilterOptionsResponse,
)
async def get_smart_filter_options() -> Any:
    """
    Retorna todas as opções de filtros baseadas nos dados reais dos participantes.
    Utiliza o cache da query principal de participantes para performance.
    """
    # Use the EXACT same query as 'get_participants' to hit the cache
    query = f"""
    SELECT 
        *
    FROM `{PROJECT_ID}.{DATASET_ID}.endpoint_participante`
    ORDER BY cpf DESC
    """
    logger.debug(f"Fetching cached data for smart filters: {query}")
    try:
        # Get DataFrame via Manager
        df = DataManager.get_dataset(query)

        if df.empty:
            return FilterOptionsResponse(options=[])

        options: List[FiltroOpcao] = []

        # Helper to add options
        def add_options(col_name: str, type_name: str, label_col: str = None):
            if col_name in df.columns:
                unique_vals = df[col_name].dropna().unique()
                for val in unique_vals:
                    # Logic to determine label (could be improved with a proper lookup map if available in DF)
                    label = str(val)

                    # Formatting
                    if type_name == "grupo":
                        label = str(val).title()
                    elif type_name == "status":
                        label = str(val).title()
                    elif type_name == "cre":
                        label = f"CRE {val}"
                    elif type_name == "cras":
                        label = f"CRAS {val}"

                    options.append(
                        FiltroOpcao(id=str(val), label=label, tipo=type_name)
                    )

        add_options("bairro", "bairro")
        add_options("id_cre", "cre")
        add_options("id_cras", "cras")
        add_options("cohort", "safra")
        add_options("grupo", "grupo")
        add_options("status", "status")

        return FilterOptionsResponse(options=options)

    except Exception as e:
        logger.error(f"Error fetching smart filter options: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
