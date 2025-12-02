from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, List, Optional

from src.core.security.jwt import verify_jwt
from src.config import env
from src.utils.bigquery import get_bigquery_result
from src.utils.log import logger

PROJECT_ID = env.BQ_PROJECT_ID
DATASET_ID = env.BQ_DATASET_ID

router = APIRouter(
    dependencies=[Depends(verify_jwt)],
)

@router.get("/equipments", summary="Filtros de Equipamentos", response_model=List[Dict[str, Any]])
async def get_equipment_filters(
    tipo: Optional[str] = Query(None, description="Filtrar por tipo (ESCOLA, CLINICA_FAMILIA, CRAS)")
) -> List[Dict[str, Any]]:
    """
    Retorna lista de equipamentos para filtros.
    """
    where_clause = f"WHERE tipo = '{tipo}'" if tipo else ""
    
    query = f"""
    SELECT 
        *
    FROM `{PROJECT_ID}.{DATASET_ID}.endpoint_filtros_equipamentos`
    {where_clause}
    ORDER BY nome
    """
    logger.debug(f"Executing query: {query}")
    try:
        return get_bigquery_result(query=query)
    except Exception as e:
        logger.error(f"Error fetching equipment filters: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/regionals", summary="Filtros Regionais", response_model=List[Dict[str, Any]])
async def get_regional_filters(
    tipo: Optional[str] = Query(None, description="Filtrar por tipo (CRE, CAP, CAS)")
) -> List[Dict[str, Any]]:
    """
    Retorna lista de regionais para filtros.
    """
    where_clause = f"WHERE tipo = '{tipo}'" if tipo else ""
    
    query = f"""
    SELECT 
        *
    FROM `{PROJECT_ID}.{DATASET_ID}.endpoint_filtros_regionais`
    {where_clause}
    ORDER BY nome
    """
    logger.debug(f"Executing query: {query}")
    try:
        return get_bigquery_result(query=query)
    except Exception as e:
        logger.error(f"Error fetching regional filters: {e}")
        raise HTTPException(status_code=500, detail=str(e))
