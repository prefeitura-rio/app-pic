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
from src.api.v1.queries import DEBUG_PARTICIPANTS_QUERY, DEBUG_ORIGINS_QUERY
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
    total_found: int  # Total de participantes encontrados na busca
    total_returned: int  # Total retornado (sempre 1 ou 0)
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

    Arquitetura Split-Table:
    1. Carrega ambas tabelas (participants + origins) do cache
    2. Filtra participants por search term
    3. Extrai unique id_origem dos participants filtrados
    4. Filtra origins pelos id_origem necessários
    5. Join participants + origins (enriquece metadata)
    6. Retorna resultado completo (apenas 1 participante)

    Retorna dados brutos incluindo:
    - Informações básicas do participante
    - Protocolos detalhados com metadata completa
    - Rastreamento de tabelas do BigQuery (tabela_bq, dbt_model_path, etc)
    - Dados intermediários de cada protocolo

    IMPORTANTE: bypass_cache=true força refresh de AMBAS tabelas.
    """
    require_super_admin(permissions)

    # Validação: search não pode ser vazio
    if not search or len(search.strip()) == 0:
        return DebugParticipantResponse(total_found=0, total_returned=0, data=[])

    search_term = search.strip()
    logger.info(f"🔍 Debug search: '{search_term}' (bypass_cache={bypass_cache})")

    try:
        # PASSO 1 & 2: Carregar AMBAS tabelas do cache (ou BigQuery se bypass_cache=True)
        df_participants, _, _ = DataManager.get_dataset(
            DEBUG_PARTICIPANTS_QUERY,
            bypass_cache=bypass_cache,
        )

        df_origins, _, _ = DataManager.get_dataset(
            DEBUG_ORIGINS_QUERY,
            bypass_cache=bypass_cache,
        )

        logger.info(f"📊 Loaded {len(df_participants)} participants, {len(df_origins)} origins")

        # PASSO 3: Filtrar participants por search term (case-insensitive)
        search_lower = search_term.lower()
        df_filtered = df_participants.filter(
            pl.col("cpf").str.to_lowercase().str.contains(search_lower) |
            pl.col("nome").str.to_lowercase().str.contains(search_lower) |
            pl.col("id_membro_familia").str.to_lowercase().str.contains(search_lower)
        )

        # Salvar total encontrado ANTES de limitar a 1
        total_found = len(df_filtered)
        logger.info(f"🔎 Found {total_found} participants matching '{search_term}'")

        # Se não achou nada, retorna vazio
        if total_found == 0:
            return DebugParticipantResponse(total_found=0, total_returned=0, data=[])

        # LIMITAÇÃO: Retornar apenas o primeiro resultado (segurança)
        df_filtered = df_filtered.head(1)

        # PASSO 4: Extrair unique id_origem dos protocolos filtrados
        # Estrutura: df_filtered tem coluna "protocolos" que é array de structs
        # Cada protocolo tem "metadata" que é array de structs com "id_origem"

        # Flatten: participante -> protocolos -> metadata -> id_origem
        try:
            unique_id_origens = (
                df_filtered
                .select("protocolos")
                .explode("protocolos")  # Um row por protocolo
                .select(pl.col("protocolos").struct.field("metadata"))
                .explode("metadata")  # Um row por metadata
                .select(pl.col("metadata").struct.field("id_origem"))
                .unique()
                .to_series()
                .to_list()
            )
        except Exception as e:
            logger.warning(f"⚠️ Erro ao extrair id_origem (estrutura vazia?): {e}")
            unique_id_origens = []

        logger.info(f"🔑 Extracted {len(unique_id_origens)} unique id_origem values")

        # PASSO 5: Filtrar origins apenas pelos id_origem necessários
        if len(unique_id_origens) > 0:
            df_origins_filtered = df_origins.filter(
                pl.col("id_origem").is_in(unique_id_origens)
            )
        else:
            df_origins_filtered = pl.DataFrame()

        logger.info(f"🗂️ Filtered to {len(df_origins_filtered)} origins")

        # PASSO 6: Join participants + origins
        # Estratégia: Enriquecer o array de metadata dentro de cada protocolo
        # com os dados de origins

        # Converter origins para dict para lookup rápido
        origins_dict = {}
        if len(df_origins_filtered) > 0:
            origins_dict = {
                row["id_origem"]: {
                    "tabela_bq": row["tabela_bq"],
                    "dbt_model_path": row["dbt_model_path"],
                    "dbt_model_type": row["dbt_model_type"],
                    "updated_at": row["updated_at"],
                    "dados_schema": row["dados_schema"],
                }
                for row in df_origins_filtered.to_dicts()
            }

        # Converter resultado para dict e enriquecer
        result = df_filtered.to_dicts()[0]  # Pega o único participante

        # Enriquecer cada protocolo com metadados completos
        for protocolo in result.get("protocolos", []):
            for metadata_item in protocolo.get("metadata", []):
                id_origem = metadata_item.get("id_origem")
                if id_origem and id_origem in origins_dict:
                    # Adiciona campos de origins ao metadata
                    metadata_item.update(origins_dict[id_origem])

        # PASSO 7: Retornar resultado
        logger.info(f"✅ Returning enriched participant data ({total_found} found, returning 1)")
        return DebugParticipantResponse(
            total_found=total_found,
            total_returned=1,
            data=[result]
        )

    except Exception as e:
        logger.error(f"❌ Erro ao buscar dados de debug: {e}")
        raise HTTPException(status_code=500, detail=str(e))
