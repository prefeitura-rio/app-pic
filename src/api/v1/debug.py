"""
Debug endpoints para super admins

Permite super admins visualizar dados de debug detalhados de participantes,
incluindo metadados de protocolos e rastreamento de tabelas do BigQuery.

REGRAS:
- Apenas super admins podem acessar
- Dados são retornados em formato bruto (JSON)
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, Any, Dict, List
import polars as pl

from src.core.security.jwt import CurrentUserPermissions
from src.utils.log import logger
from src.utils.data_manager import DataManager
from src.api.v1.queries import DEBUG_PARTICIPANTS_QUERY
from src.api.v1.schemas import PaginatedResponse, PaginationParams
from pydantic import BaseModel

router = APIRouter(
    prefix="/debug",
    tags=["Debug"],
)


# ========================================================================
# SCHEMAS
# ========================================================================

class DebugParticipantResponse(BaseModel):
    """Response para dados de debug de um participante"""
    data: List[Dict[str, Any]]  # Raw JSON data from BigQuery


# ========================================================================
# HELPERS
# ========================================================================

def require_super_admin(permissions: CurrentUserPermissions):
    """Valida que usuário é super admin"""
    if not permissions.is_super_admin:
        raise HTTPException(
            status_code=403,
            detail="Acesso negado: apenas super admins podem acessar dados de debug",
        )


# ========================================================================
# ENDPOINTS
# ========================================================================

@router.get("/participants", response_model=DebugParticipantResponse)
async def get_debug_participants(
    permissions: CurrentUserPermissions,
    search: Optional[str] = Query(None, description="Buscar por CPF, nome ou ID membro família"),
    bypass_cache: bool = Query(False, description="Se true, força dados frescos do BigQuery"),
):
    """
    Busca dados de debug de participantes (SUPER ADMIN ONLY).

    Retorna dados brutos da tabela de debug incluindo:
    - Informações básicas do participante
    - Protocolos detalhados com metadata
    - Rastreamento de tabelas do BigQuery
    - Dados intermediários de cada protocolo

    IMPORTANTE: Apenas super admins podem acessar este endpoint.
    """
    require_super_admin(permissions)

    logger.info(f"Super admin buscando dados de debug - search: {search}")

    if not search or len(search.strip()) == 0:
        # Sem busca, retornar vazio (endpoint reativo)
        return DebugParticipantResponse(data=[])

    search_term = search.strip()

    try:
        # Buscar usando DataManager (com cache e polars)
        # Buscar em CPF, nome, id_membro_familia
        df_data, meta, filter_options = DataManager.fetch_filter_paginate(
            query=DEBUG_PARTICIPANTS_QUERY,
            filters_dict={},
            page=1,
            page_size=100,  # Limite de 100 resultados
            search_term=search_term,
            search_columns=["cpf", "nome", "id_membro_familia"],
            filter_columns_config={},  # Sem filtros em cascata
            user_permissions=None,  # Sem governança (super admin vê tudo)
            bypass_cache=bypass_cache,
        )

        # Converter para dicts (mantém estrutura JSON do BQ)
        results = df_data.to_dicts() if not df_data.is_empty() else []

        logger.info(f"Debug search retornou {len(results)} resultados")

        return DebugParticipantResponse(data=results)

    except Exception as e:
        logger.error(f"Erro ao buscar dados de debug: {e}")
        raise HTTPException(status_code=500, detail=str(e))
