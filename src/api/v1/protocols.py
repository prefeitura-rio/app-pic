from fastapi import APIRouter, Depends, HTTPException
from typing import Any

from src.core.security.jwt import verify_jwt
from src.config import env
from src.utils.log import logger
from src.api.v1.schemas import ProtocoloResumo, PaginatedResponse
from src.utils.data_manager import DataManager

PROJECT_ID = env.BQ_PROJECT_ID
DATASET_ID = env.BQ_DATASET_ID

router = APIRouter(
    dependencies=[Depends(verify_jwt)],
)


@router.get("/summary", summary="Resumo de Protocolos", response_model=PaginatedResponse[ProtocoloResumo])
async def get_protocols_summary() -> Any:
    """
    Retorna resumo de violações de protocolos.
    """
    query = f"""
    SELECT 
        *
    FROM `{PROJECT_ID}.{DATASET_ID}.endpoint_protocolo_resumo`
    """
    logger.debug(f"Fetching cached data for protocols summary: {query}")
    try:
        df_data, meta, filter_options = DataManager.fetch_filter_paginate(
            query=query,
            filters_dict={},  # Sem filtros
            page=1,
            page_size=10000,
            filter_columns_config=None,
        )

        # OTIMIZAÇÃO: Converter DataFrame para JSON apenas aqui (última etapa)
        data_json = DataManager.df_to_json(df_data)

        return PaginatedResponse(
            data=data_json,
            meta=meta,
            filters=filter_options,
        )

    except Exception as e:
        logger.error(f"Error fetching protocols summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))
