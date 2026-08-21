"""
Debug endpoints para super admins

Permite super admins visualizar dados de debug detalhados de participantes,
incluindo metadados de protocolos e rastreamento de tabelas do BigQuery.

REGRAS:
- Apenas super admins podem acessar
- Dados são retornados em formato bruto (JSON)
"""

from typing import Any

import polars as pl
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.api.v1.queries import DEBUG_ORIGINS_QUERY, PARTICIPANTS_TABLE_QUERY
from src.config import env
from src.core.security.jwt import CurrentUserPermissions
from src.utils.bigquery import execute_query
from src.utils.data_manager import DataManager
from src.utils.log import logger

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
    data: list[dict[str, Any]]  # Raw JSON data from BigQuery


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
    search: str | None = Query(
        None, description="Buscar por CPF, nome ou ID membro família"
    ),
    bypass_cache: bool = Query(
        False, description="Se true, força dados frescos do BigQuery"
    ),
):
    """
    Busca dados de debug de participantes (SUPER ADMIN ONLY).

    Nova arquitetura otimizada:
    1. Busca na tabela de listagem individual por search term
    2. Extrai CPFs dos resultados
    3. Converte CPF → cpf_particao (int)
    4. Query filtrada no BigQuery: WHERE cpf_particao IN (...)
    5. Busca origins e faz join

    Retorna dados brutos incluindo:
    - Informações básicas do participante
    - Protocolos detalhados com metadata completa
    - Rastreamento de tabelas do BigQuery (tabela_bq, dbt_model_path, etc)
    - Dados intermediários de cada protocolo

    IMPORTANTE: bypass_cache=true força refresh da tabela de listagem e origins.
    """
    require_super_admin(permissions)

    # Validação: search não pode ser vazio
    if not search or len(search.strip()) == 0:
        return DebugParticipantResponse(total_found=0, total_returned=0, data=[])

    search_term = search.strip()
    logger.info(f"🔍 Debug search: '{search_term}' (bypass_cache={bypass_cache})")

    try:
        # PASSO 1: Buscar na tabela de listagem individual
        df_listagem, _, _ = await DataManager.get_dataset(
            PARTICIPANTS_TABLE_QUERY,
            bypass_cache=bypass_cache,
        )

        logger.info(f"📊 Loaded {len(df_listagem)} participants from listagem")

        # PASSO 2: Filtrar por search term (case-insensitive)
        search_lower = search_term.lower()
        df_search_results = df_listagem.filter(
            pl.col("cpf").str.to_lowercase().str.contains(search_lower)
            | pl.col("nome").str.to_lowercase().str.contains(search_lower)
            | pl.col("id_membro_familia").str.to_lowercase().str.contains(search_lower)
        )

        # Salvar total encontrado ANTES de limitar
        total_found = len(df_search_results)
        logger.info(f"🔎 Found {total_found} participants matching '{search_term}'")

        # Se não achou nada, retorna vazio
        if total_found == 0:
            return DebugParticipantResponse(total_found=0, total_returned=0, data=[])

        # LIMITAÇÃO: Pegar apenas o primeiro resultado (segurança)
        df_search_results = df_search_results.head(1)

        # PASSO 3: Extrair CPFs e converter para cpf_particao (int)
        cpfs_str = df_search_results.select("cpf").to_series().to_list()

        # Converter CPF string (###.###.###-##) para int
        cpfs_particao = []
        for cpf_str in cpfs_str:
            if cpf_str:
                # Remover pontos e traços, converter para int
                cpf_int = int(cpf_str.replace(".", "").replace("-", ""))
                cpfs_particao.append(cpf_int)

        if not cpfs_particao:
            logger.warning("⚠️ Nenhum CPF válido encontrado")
            return DebugParticipantResponse(total_found=0, total_returned=0, data=[])

        logger.info("🔢 Converted CPFs to cpf_particao")

        # PASSO 4: Query filtrada no BigQuery para tabela DEBUG
        cpf_list_str = ",".join(str(cpf) for cpf in cpfs_particao)
        debug_query = f"""
        SELECT *
        FROM `{env.BQ_PROJECT_ID}.{env.BQ_DATASET_ID}.{env.BQ_TABLE_ID_PARTICIPANTS_DEBUG}`
        WHERE cpf_particao IN ({cpf_list_str})
        ORDER BY nome ASC
        """

        logger.info("🔍 Fetching debug data for cpf_particao using partitioned query!")
        df_participants = execute_query(debug_query)

        if len(df_participants) == 0:
            logger.warning("⚠️ Nenhum dado de debug encontrado para os CPFs")
            return DebugParticipantResponse(
                total_found=total_found, total_returned=0, data=[]
            )

        # Pegar apenas o primeiro resultado
        df_filtered = df_participants.head(1)
        logger.info("✅ Found debug data for participant")

        # PASSO 5: Extrair unique protocolo_id dos protocolos filtrados
        try:
            unique_protocolo_ids = (
                df_filtered.select("protocolos")
                .explode("protocolos")
                .select(pl.col("protocolos").struct.field("protocolo_id"))
                .unique()
                .to_series()
                .to_list()
            )
        except Exception as e:
            logger.warning(f"⚠️ Erro ao extrair protocolo_id (estrutura vazia?): {e}")
            unique_protocolo_ids = []

        logger.info(
            f"🔑 Extracted {len(unique_protocolo_ids)} unique protocolo_id values"
        )

        # PASSO 6: Buscar origins (cacheable)
        df_origins, _, _ = await DataManager.get_dataset(
            DEBUG_ORIGINS_QUERY,
            bypass_cache=bypass_cache,
        )

        # Filtrar origins apenas pelos protocolo_id necessários
        if len(unique_protocolo_ids) > 0:
            df_origins_filtered = df_origins.filter(
                pl.col("protocolo_id").is_in(unique_protocolo_ids)
            )
        else:
            df_origins_filtered = pl.DataFrame()

        logger.info(f"🗂️ Filtered to {len(df_origins_filtered)} origin protocols")

        # PASSO 7: Join participants + origins
        # Nova estrutura: origins tem 1 linha por protocolo_id com array tabelas_fonte[]
        # Precisamos explodir tabelas_fonte[] para criar lookup por id_origem

        # Construir lookup dicts
        origins_dict = {}  # id_origem -> origin metadata
        regras_negocio_dict = {}  # protocolo_id -> regras_negocio

        if len(df_origins_filtered) > 0:
            # Explodir tabelas_fonte[] para ter 1 linha por origem
            df_origins_exploded = df_origins_filtered.select(
                ["protocolo_id", "tabelas_fonte", "regras_negocio"]
            ).explode("tabelas_fonte")

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

        # PASSO 8: Retornar resultado
        logger.info(
            f"✅ Returning enriched participant data ({total_found} found, returning 1)"
        )
        return DebugParticipantResponse(
            total_found=total_found, total_returned=1, data=[result]
        )

    except Exception as e:
        logger.error(f"❌ Erro ao buscar dados de debug: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
