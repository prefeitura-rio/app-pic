from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Any
import polars as pl
import time

from src.core.security.jwt import verify_jwt, CurrentUserPermissions
from src.utils.log import logger
from src.api.v1.schemas import (
    Dashboard,
    PaginatedResponse,
    CommonFilters,
    DistribuicaoGrupo,
    DistribuicaoBairro,
    DistribuicaoMotivoSaida,
    DistribuicaoSafra,
    ResultadoProgramaPoint,
)
from src.utils.data_manager import DataManager
from src.api.v1.queries import PARTICIPANTS_TABLE_QUERY

router = APIRouter(dependencies=[Depends(verify_jwt)], tags=["Dashboard"])

# Configuração de filtros para dashboard (IDÊNTICA ao participants para cache sharing)
DASHBOARD_FILTER_COLUMN_MAP = {
    "bairro": "bairro",
    "cre": "id_cre",
    "ap": "id_ap",  # ATUALIZADO: AP substitui CAP
    "cas": "id_cas",
    "cras": "id_cras",
    "escola": "id_escola",
    "clinica": "id_clinica_familia",
    "safra": "cohort",
    "grupo": "grupo",
    "status": "status",
    "situacao": "situacao",
}

# Filter options config (IDÊNTICA ao participants)
DASHBOARD_FILTER_OPTIONS_CONFIG = {
    "bairros": {"column": "bairro"},
    "grupos": {"column": "grupo"},
    "cohorts": {"column": "cohort"},
    "status_list": {"column": "status"},
    "situacoes": {"column": "situacao"},
    "cres": {"column": "id_cre", "label_column": "nome_cre"},
    "aps": {"column": "id_ap", "label_column": "nome_ap"},  # ATUALIZADO: caps → aps, CAP → AP
    "cas_list": {"column": "id_cas", "label_column": "nome_cas"},
    "cras": {"column": "id_cras", "label_column": "nome_cras"},
    "escolas": {"column": "id_escola", "label_column": "nome_escola"},
    "clinicas": {
        "column": "id_clinica_familia",
        "label_column": "nome_clinica_familia",
    },
}


@router.get(
    "/dashboard",
    summary="Métricas do Dashboard",
    response_model=PaginatedResponse[Dashboard],
)
async def get_dashboard_metrics(
    permissions: CurrentUserPermissions,
    filters: CommonFilters = Depends(),
    bypass_cache: bool = Query(False, description="Forçar refresh do cache"),
) -> Any:
    """
    Retorna métricas agregadas para o dashboard principal com suporte a filtros.

    Arquitetura Otimizada para Cache:
    - USA A MESMA QUERY que /participants para REUTILIZAR O CACHE
    - Evita concorrência de queries no BigQuery
    - Busca TODOS os dados filtrados (sem paginação)
    - Calcula métricas agregadas em tempo real usando Polars
    - Retorna Dashboard com todas as métricas e distribuições

    IMPORTANTE: A query é idêntica à de /participants para garantir cache hit.
    """

    # MESMA QUERY que /participants - CRÍTICO para cache sharing
    query = PARTICIPANTS_TABLE_QUERY
    per = permissions.model_dump(exclude_none=True)
    per_log = {
        "cpf": per.get("cpf"),
        "is_admin": per.get("is_admin"),
        "is_super_admin": per.get("is_super_admin"),
        "active": per.get("active"),
    }
    logger.info("Fetching dashboard metrics with filters (using participants cache)")
    logger.info(f"🔑 Permissions: {per_log}")
    logger.info(f"☰ Filters: {filters.model_dump(exclude_none=True)}")
    logger.info(f"🔄 Bypass Cache: {bypass_cache}")

    try:
        # Converter filtros de API para colunas do DataFrame
        filters_dict = filters.model_dump(exclude_none=True)
        # Remove search pois não é usado no dashboard
        filters_dict.pop("search", None)

        column_filters = {}
        for filter_key, filter_value in filters_dict.items():
            if filter_key in DASHBOARD_FILTER_COLUMN_MAP:
                column_name = DASHBOARD_FILTER_COLUMN_MAP[filter_key]
                column_filters[column_name] = filter_value

        # Usar fetch_filter_paginate com page_size=None para:
        # 1. Reutilizar cache compartilhado com /participants
        # 2. Aplicar filtros
        # 3. Calcular filter options com cascata inteligente
        # 4. Retornar TODOS os dados filtrados (sem paginação)
        # Se bypass_cache=True, força query no BigQuery para garantir dados frescos
        df_data, meta, filter_options = DataManager.fetch_filter_paginate(
            query=query,
            filters_dict=column_filters,
            page=1,
            page_size=None,  # None = retorna TODOS os dados sem paginação
            filter_columns_config=DASHBOARD_FILTER_OPTIONS_CONFIG,
            user_permissions=permissions,
            bypass_cache=bypass_cache,  # IMPORTANTE: Passa bypass_cache para forçar refresh
        )

        # OTIMIZAÇÃO V2: fetch_filter_paginate agora retorna Polars diretamente
        # Não precisa mais converter de Pandas
        df = df_data  # Já é Polars DataFrame

        # Se vazio, retornar métricas zeradas
        if df.is_empty():
            empty_dashboard = Dashboard(
                total_participantes_ativos=0,
                total_participantes_inativos=0,
                total_participantes_geral=0,
                total_participantes_regulares=0,
                total_participantes_irregulares=0,
                percentual_regular=0.0,
                percentual_irregular=0.0,
                total_participantes_em_atencao=0,
                percentual_em_atencao=0.0,
                total_protocolos=0,
                total_protocolos_irregular=0,
                percentual_protocolos_irregular=0.0,
                total_protocolos_smas=0,
                total_protocolos_smas_irregular=0,
                percentual_smas_irregular=0.0,
                total_protocolos_sme=0,
                total_protocolos_sme_irregular=0,
                percentual_sme_irregular=0.0,
                total_protocolos_sms=0,
                total_protocolos_sms_irregular=0,
                percentual_sms_irregular=0.0,
                assistencia_completude_total=0,
                assistencia_completude_percentual=0.0,
                educacao_completude_total=0,
                educacao_completude_percentual=0.0,
                saude_completude_total=0,
                saude_completude_percentual=0.0,
                distribuicao_por_grupo=[],
                top_bairros=[],
                distribuicao_motivo_saida=[],
                distribuicao_por_safra=[],
            )
            return PaginatedResponse(
                meta=meta,
                data=[empty_dashboard],
                filters=filter_options,
            )

        # Calcular métricas agregadas
        metrics_start = time.perf_counter()
        dashboard_metrics = _calculate_dashboard_metrics(df)
        metrics_time = time.perf_counter() - metrics_start

        logger.info(f"⏱️ [TIMING] Metrics calculation: {metrics_time:.3f}s")
        logger.info(
            f"Dashboard metrics calculated for {len(df)} participants "
            f"(cache_hit={meta.cache_hit})"
        )

        # Retornar como PaginatedResponse com um único item
        # IMPORTANTE: Incluir filter options com cascata inteligente
        return PaginatedResponse(
            meta=meta,
            data=[dashboard_metrics],
            filters=filter_options,
        )

    except Exception as e:
        logger.error(f"❌ Error fetching dashboard metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _calculate_dashboard_metrics(df: pl.DataFrame) -> Dashboard:
    """
    Calcula todas as métricas do dashboard a partir do DataFrame de participantes.

    Args:
        df: Polars DataFrame com dados de participantes

    Returns:
        Dashboard object com todas as métricas calculadas
    """
    # Totais básicos
    total_geral = len(df)
    total_ativos = df.filter(pl.col("status") == "ativo").height
    total_inativos = total_geral - total_ativos

    # Métricas principais: Regular/Irregular
    # Regular = participante com 0 protocolos irregulares
    # Irregular = participante com >= 1 protocolo irregular
    total_regulares = (
        df.filter(pl.col("total_protocolos_irregular") == 0).height
        if "total_protocolos_irregular" in df.columns
        else 0
    )
    total_irregulares = total_geral - total_regulares

    # Percentuais
    perc_regular = (total_regulares / total_geral * 100) if total_geral > 0 else 0.0
    perc_irregular = (total_irregulares / total_geral * 100) if total_geral > 0 else 0.0

    # Participantes em atenção (situacao contém "atenção" ou "irregular")
    em_atencao = (
        df.filter(
            (pl.col("situacao").str.to_lowercase().str.contains("atenção"))
            | (pl.col("situacao").str.to_lowercase().str.contains("irregular"))
        ).height
        if "situacao" in df.columns
        else 0
    )

    # Protocolos totais
    total_protocolos = (
        df["total_protocolos"].sum() if "total_protocolos" in df.columns else 0
    )
    total_irregular = (
        df["total_protocolos_irregular"].sum()
        if "total_protocolos_irregular" in df.columns
        else 0
    )

    # Protocolos por secretaria
    total_smas = (
        df["assistencia_protocolos_total"].sum()
        if "assistencia_protocolos_total" in df.columns
        else 0
    )
    irregular_smas = (
        df["assistencia_protocolos_irregular"].sum()
        if "assistencia_protocolos_irregular" in df.columns
        else 0
    )

    total_sme = (
        df["educacao_protocolos_total"].sum()
        if "educacao_protocolos_total" in df.columns
        else 0
    )
    irregular_sme = (
        df["educacao_protocolos_irregular"].sum()
        if "educacao_protocolos_irregular" in df.columns
        else 0
    )

    total_sms = (
        df["saude_protocolos_total"].sum()
        if "saude_protocolos_total" in df.columns
        else 0
    )
    irregular_sms = (
        df["saude_protocolos_irregular"].sum()
        if "saude_protocolos_irregular" in df.columns
        else 0
    )

    # Distribuição por grupo
    distribuicao_grupo = []
    if "grupo" in df.columns:
        grupo_counts = df.group_by("grupo").agg(pl.count().alias("total_participantes"))
        distribuicao_grupo = [
            DistribuicaoGrupo(
                grupo=row["grupo"], total_participantes=row["total_participantes"]
            )
            for row in grupo_counts.to_dicts()
            if row["grupo"] is not None
        ]

    # Top bairros (top 10)
    top_bairros = []
    if "bairro" in df.columns:
        bairro_counts = (
            df.group_by("bairro")
            .agg(pl.count().alias("total_participantes"))
            .sort("total_participantes", descending=True)
            .head(10)
        )
        top_bairros = [
            DistribuicaoBairro(
                bairro=row["bairro"], total_participantes=row["total_participantes"]
            )
            for row in bairro_counts.to_dicts()
            if row["bairro"] is not None
        ]

    # Distribuição por safra (com ativos/inativos)
    distribuicao_safra = []
    if "cohort" in df.columns:
        # Converter cohort para string se for date
        df_safra = df.with_columns(pl.col("cohort").cast(pl.Utf8).alias("safra"))
        safra_counts = df_safra.group_by("safra").agg(
            pl.count().alias("total_participantes"),
            pl.col("status")
            .filter(pl.col("status") == "ativo")
            .count()
            .alias("total_ativos"),
            pl.col("status")
            .filter(pl.col("status") != "ativo")
            .count()
            .alias("total_inativos"),
        )
        distribuicao_safra = [
            DistribuicaoSafra(
                safra=row["safra"],
                total_participantes=row["total_participantes"],
                total_ativos=row["total_ativos"],
                total_inativos=row["total_inativos"],
            )
            for row in safra_counts.to_dicts()
            if row["safra"] is not None
        ]

    # Distribuição motivo saída (apenas inativos)
    distribuicao_motivo = []
    if "status_inativo_motivo" in df.columns:
        df_inativos = df.filter(pl.col("status") != "ativo")
        if len(df_inativos) > 0:
            motivo_counts = df_inativos.group_by("status_inativo_motivo").agg(
                pl.count().alias("total")
            )
            distribuicao_motivo = [
                DistribuicaoMotivoSaida(
                    motivo=row["status_inativo_motivo"], total=row["total"]
                )
                for row in motivo_counts.to_dicts()
                if row["status_inativo_motivo"] is not None
            ]

    # Calcular percentuais
    perc_atencao = (em_atencao / total_geral * 100) if total_geral > 0 else 0.0
    perc_protocolos_irregular = (
        (total_irregular / total_protocolos * 100) if total_protocolos > 0 else 0.0
    )
    perc_smas_irregular = (irregular_smas / total_smas * 100) if total_smas > 0 else 0.0
    perc_sme_irregular = (irregular_sme / total_sme * 100) if total_sme > 0 else 0.0
    perc_sms_irregular = (irregular_sms / total_sms * 100) if total_sms > 0 else 0.0

    # ===== DIMENSÃO ASSISTÊNCIA SOCIAL =====
    # Completude Assistência (0 protocolos irregulares)
    assistencia_completude_total = (
        df.filter(pl.col("assistencia_protocolos_irregular") == 0).height
        if "assistencia_protocolos_irregular" in df.columns
        else 0
    )
    assistencia_completude_perc = (
        (assistencia_completude_total / total_geral * 100) if total_geral > 0 else 0.0
    )

    # ===== DIMENSÃO EDUCAÇÃO =====
    # Completude Educação (0 protocolos irregulares)
    educacao_completude_total = (
        df.filter(pl.col("educacao_protocolos_irregular") == 0).height
        if "educacao_protocolos_irregular" in df.columns
        else 0
    )
    educacao_completude_perc = (
        (educacao_completude_total / total_geral * 100) if total_geral > 0 else 0.0
    )

    # ===== DIMENSÃO SAÚDE =====
    # Completude Saúde (0 protocolos irregulares)
    saude_completude_total = (
        df.filter(pl.col("saude_protocolos_irregular") == 0).height
        if "saude_protocolos_irregular" in df.columns
        else 0
    )
    saude_completude_perc = (
        (saude_completude_total / total_geral * 100) if total_geral > 0 else 0.0
    )

    # ===== RESULTADO DO PROGRAMA (Evolução Temporal) =====
    resultado_programa = _calculate_resultado_programa(df)

    return Dashboard(
        # Totais básicos
        total_participantes_ativos=total_ativos,
        total_participantes_inativos=total_inativos,
        total_participantes_geral=total_geral,
        # Métricas principais
        total_participantes_regulares=total_regulares,
        total_participantes_irregulares=total_irregulares,
        percentual_regular=perc_regular,
        percentual_irregular=perc_irregular,
        # Métricas antigas
        total_participantes_em_atencao=em_atencao,
        percentual_em_atencao=perc_atencao,
        # Protocolos gerais
        total_protocolos=int(total_protocolos) if total_protocolos else 0,
        total_protocolos_irregular=int(total_irregular) if total_irregular else 0,
        percentual_protocolos_irregular=perc_protocolos_irregular,
        # Protocolos por dimensão
        total_protocolos_smas=int(total_smas) if total_smas else 0,
        total_protocolos_smas_irregular=int(irregular_smas) if irregular_smas else 0,
        percentual_smas_irregular=perc_smas_irregular,
        total_protocolos_sme=int(total_sme) if total_sme else 0,
        total_protocolos_sme_irregular=int(irregular_sme) if irregular_sme else 0,
        percentual_sme_irregular=perc_sme_irregular,
        total_protocolos_sms=int(total_sms) if total_sms else 0,
        total_protocolos_sms_irregular=int(irregular_sms) if irregular_sms else 0,
        percentual_sms_irregular=perc_sms_irregular,
        # Dimensão Assistência Social
        assistencia_completude_total=assistencia_completude_total,
        assistencia_completude_percentual=assistencia_completude_perc,
        # Dimensão Educação
        educacao_completude_total=educacao_completude_total,
        educacao_completude_percentual=educacao_completude_perc,
        # Dimensão Saúde
        saude_completude_total=saude_completude_total,
        saude_completude_percentual=saude_completude_perc,
        # Distribuições
        distribuicao_por_grupo=distribuicao_grupo,
        top_bairros=top_bairros,
        distribuicao_motivo_saida=distribuicao_motivo,
        distribuicao_por_safra=distribuicao_safra,
        # Resultado do Programa
        resultado_programa=resultado_programa,
    )


def _calculate_resultado_programa(df: pl.DataFrame) -> list[ResultadoProgramaPoint]:
    """
    Calcula evolução temporal do programa por dimensão.

    OTIMIZADO: Usa group_by ao invés de loop por cohort.
    Antes: O(cohorts * rows) - ~3.8s para 149k rows
    Depois: O(rows) - ~0.1s

    Args:
        df: Polars DataFrame com dados de participantes

    Returns:
        Lista de pontos temporais com completude por dimensão
    """
    if df.is_empty() or "cohort" not in df.columns:
        return []

    # Verificar colunas disponíveis uma vez
    has_total_irregular = "total_protocolos_irregular" in df.columns
    has_saude_irregular = "saude_protocolos_irregular" in df.columns
    has_educacao_irregular = "educacao_protocolos_irregular" in df.columns
    has_assistencia_irregular = "assistencia_protocolos_irregular" in df.columns

    # OTIMIZAÇÃO: Usar group_by com agregações condicionais (single pass)
    df_tempo = df.with_columns(pl.col("cohort").cast(pl.Utf8).alias("mes"))

    # Construir agregações dinamicamente baseado nas colunas disponíveis
    aggs = [pl.count().alias("total")]

    if has_total_irregular:
        aggs.append(
            (pl.col("total_protocolos_irregular") == 0).sum().alias("regulares")
        )
    if has_saude_irregular:
        aggs.append(
            (pl.col("saude_protocolos_irregular") == 0).sum().alias("saude_ok")
        )
    if has_educacao_irregular:
        aggs.append(
            (pl.col("educacao_protocolos_irregular") == 0).sum().alias("educacao_ok")
        )
    if has_assistencia_irregular:
        aggs.append(
            (pl.col("assistencia_protocolos_irregular") == 0).sum().alias("assistencia_ok")
        )

    # Single group_by operation (muito mais rápido que loop)
    result_df = (
        df_tempo.filter(pl.col("mes").is_not_null())
        .group_by("mes")
        .agg(aggs)
        .sort("mes")
    )

    # Converter para lista de ResultadoProgramaPoint
    resultado = []
    for row in result_df.to_dicts():
        total = row["total"]
        if total == 0:
            continue

        regulares = row.get("regulares", 0) or 0
        saude_ok = row.get("saude_ok", 0) or 0
        educacao_ok = row.get("educacao_ok", 0) or 0
        assistencia_ok = row.get("assistencia_ok", 0) or 0

        resultado.append(
            ResultadoProgramaPoint(
                mes=row["mes"],
                todos=round(regulares / total * 100, 1),
                saude=round(saude_ok / total * 100, 1),
                educacao=round(educacao_ok / total * 100, 1),
                assistencia=round(assistencia_ok / total * 100, 1),
            )
        )

    return resultado
