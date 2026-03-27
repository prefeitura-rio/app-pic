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

        # PASSO 4: Extrair unique protocolo_id dos protocolos filtrados
        # Estrutura: df_filtered tem coluna "protocolos" que é array de structs
        # Cada protocolo tem "protocolo_id"

        # Flatten: participante -> protocolos -> protocolo_id
        try:
            unique_protocolo_ids = (
                df_filtered
                .select("protocolos")
                .explode("protocolos")  # Um row por protocolo
                .select(pl.col("protocolos").struct.field("protocolo_id"))
                .unique()
                .to_series()
                .to_list()
            )
        except Exception as e:
            logger.warning(f"⚠️ Erro ao extrair protocolo_id (estrutura vazia?): {e}")
            unique_protocolo_ids = []

        logger.info(f"🔑 Extracted {len(unique_protocolo_ids)} unique protocolo_id values")

        # PASSO 5: Filtrar origins apenas pelos protocolo_id necessários
        # Nova estrutura: origins tem 1 linha por protocolo_id com array tabelas_fonte[]
        if len(unique_protocolo_ids) > 0:
            df_origins_filtered = df_origins.filter(
                pl.col("protocolo_id").is_in(unique_protocolo_ids)
            )
        else:
            df_origins_filtered = pl.DataFrame()

        logger.info(f"🗂️ Filtered to {len(df_origins_filtered)} origin protocols")

        # PASSO 6: Join participants + origins
        # Nova estrutura: origins tem 1 linha por protocolo_id com array tabelas_fonte[]
        # Precisamos explodir tabelas_fonte[] para criar lookup por id_origem

        # Construir lookup dicts
        origins_dict = {}  # id_origem -> origin metadata
        regras_negocio_dict = {}  # protocolo_id -> regras_negocio

        if len(df_origins_filtered) > 0:
            # Explodir tabelas_fonte[] para ter 1 linha por origem
            df_origins_exploded = df_origins_filtered.select([
                "protocolo_id",
                "tabelas_fonte",
                "regras_negocio"
            ]).explode("tabelas_fonte")

            # Construir origins_dict: id_origem -> metadata
            for row in df_origins_exploded.to_dicts():
                tabela_fonte = row.get("tabelas_fonte")
                if tabela_fonte:
                    id_origem = tabela_fonte.get("id_origem")
                    if id_origem:
                        origins_dict[id_origem] = {
                            "tabela_bq": tabela_fonte.get("tabela_bq"),
                            "dbt_model_path": tabela_fonte.get("dbt_model_path"),
                            "dbt_model_type": tabela_fonte.get("dbt_model_type"),
                            "updated_at": tabela_fonte.get("updated_at"),
                            "dados_schema": tabela_fonte.get("dados_schema"),
                        }

            # Construir regras_negocio_dict: protocolo_id -> regras_negocio
            for row in df_origins_filtered.to_dicts():
                protocolo_id = row.get("protocolo_id")
                regras_negocio = row.get("regras_negocio")
                if protocolo_id and regras_negocio:
                    regras_negocio_dict[protocolo_id] = regras_negocio

        # Converter resultado para dict e enriquecer
        result = df_filtered.to_dicts()[0]  # Pega o único participante

        # Enriquecer cada protocolo com metadados completos e regras de negócio
        for protocolo in result.get("protocolos", []):
            # Adicionar regras_negocio ao protocolo
            protocolo_id = protocolo.get("protocolo_id")
            if protocolo_id and protocolo_id in regras_negocio_dict:
                protocolo["regras_negocio"] = regras_negocio_dict[protocolo_id]

            # Enriquecer metadata com dados de origem
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
