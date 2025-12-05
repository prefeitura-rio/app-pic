from fastapi import APIRouter, Depends, HTTPException
from typing import Any
import polars as pl

from src.core.security.jwt import verify_jwt
from src.config import env
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

PROJECT_ID = env.BQ_PROJECT_ID
DATASET_ID = env.BQ_DATASET_ID

router = APIRouter(
    dependencies=[Depends(verify_jwt)],
)

# Configuração de filtros para dashboard (IDÊNTICA ao participants para cache sharing)
DASHBOARD_FILTER_COLUMN_MAP = {
    "bairro": "bairro",
    "cre": "id_cre",
    "cap": "id_cap",
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
    "caps": {"column": "id_cap", "label_column": "nome_cap"},
    "cas_list": {"column": "id_cas", "label_column": "nome_cas"},
    "cras": {"column": "id_cras", "label_column": "nome_cras"},
    "escolas": {"column": "id_escola", "label_column": "nome_escola"},
    "clinicas": {
        "column": "id_clinica_familia",
        "label_column": "nome_clinica_familia",
    },
}


@router.get(
    "/", summary="Métricas do Dashboard", response_model=PaginatedResponse[Dashboard]
)
async def get_dashboard_metrics(filters: CommonFilters = Depends()) -> Any:
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
    query = f"""
    SELECT
        *
    FROM `{PROJECT_ID}.{DATASET_ID}.endpoint_participante`
    ORDER BY nome ASC
    """

    logger.info("Fetching dashboard metrics with filters (using participants cache)")
    logger.info(f"Filters: {filters.model_dump(exclude_none=True)}")

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
        df_data, meta, filter_options = DataManager.fetch_filter_paginate(
            query=query,
            filters_dict=column_filters,
            page=1,
            page_size=None,  # None = retorna TODOS os dados sem paginação
            filter_columns_config=DASHBOARD_FILTER_OPTIONS_CONFIG,
        )

        # OTIMIZAÇÃO: Converter Pandas DataFrame para Polars para cálculos eficientes
        # Polars é ~10x mais rápido que Pandas para agregações
        # IMPORTANTE: Converter category dtype para string antes (Polars não suporta category)
        df_pandas = df_data.copy()
        for col in df_pandas.select_dtypes(include=["category"]).columns:
            df_pandas[col] = df_pandas[col].astype(str)

        df = pl.from_pandas(df_pandas)

        logger.info(
            f"Dashboard metrics calculated for {len(df)} participants "
            f"(cache_hit={meta.cache_hit})"
        )

        # Se vazio, retornar métricas zeradas
        if len(df) == 0:
            empty_dashboard = Dashboard(
                total_participantes_ativos=0,
                total_participantes_inativos=0,
                total_participantes_geral=0,
                total_participantes_em_atencao=0,
                percentual_em_atencao=0.0,
                total_protocolos=0,
                total_protocolos_violados=0,
                percentual_protocolos_violados=0.0,
                total_protocolos_smas=0,
                total_protocolos_smas_violados=0,
                percentual_smas_violados=0.0,
                total_protocolos_sme=0,
                total_protocolos_sme_violados=0,
                percentual_sme_violados=0.0,
                total_protocolos_sms=0,
                total_protocolos_sms_violados=0,
                percentual_sms_violados=0.0,
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
        dashboard_metrics = _calculate_dashboard_metrics(df)

        # Retornar como PaginatedResponse com um único item
        # IMPORTANTE: Incluir filter options com cascata inteligente
        return PaginatedResponse(
            meta=meta,
            data=[dashboard_metrics],
            filters=filter_options,
        )

    except Exception as e:
        logger.error(f"Error fetching dashboard metrics: {e}")
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
    # Regular = participante com 0 protocolos violados
    # Irregular = participante com >= 1 protocolo violado
    total_regulares = (
        df.filter(pl.col("total_protocolos_violados") == 0).height
        if "total_protocolos_violados" in df.columns
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
    total_violados = (
        df["total_protocolos_violados"].sum()
        if "total_protocolos_violados" in df.columns
        else 0
    )

    # Protocolos por secretaria
    total_smas = (
        df["assistencia_protocolos_total"].sum()
        if "assistencia_protocolos_total" in df.columns
        else 0
    )
    violados_smas = (
        df["assistencia_protocolos_violados"].sum()
        if "assistencia_protocolos_violados" in df.columns
        else 0
    )

    total_sme = (
        df["educacao_protocolos_total"].sum()
        if "educacao_protocolos_total" in df.columns
        else 0
    )
    violados_sme = (
        df["educacao_protocolos_violados"].sum()
        if "educacao_protocolos_violados" in df.columns
        else 0
    )

    total_sms = (
        df["saude_protocolos_total"].sum()
        if "saude_protocolos_total" in df.columns
        else 0
    )
    violados_sms = (
        df["saude_protocolos_violados"].sum()
        if "saude_protocolos_violados" in df.columns
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

    # Calcular percentuais antigos (manter compatibilidade)
    perc_atencao = (em_atencao / total_geral * 100) if total_geral > 0 else 0.0
    perc_protocolos_violados = (
        (total_violados / total_protocolos * 100) if total_protocolos > 0 else 0.0
    )
    perc_smas_violados = (violados_smas / total_smas * 100) if total_smas > 0 else 0.0
    perc_sme_violados = (violados_sme / total_sme * 100) if total_sme > 0 else 0.0
    perc_sms_violados = (violados_sms / total_sms * 100) if total_sms > 0 else 0.0

    # ===== DIMENSÃO ASSISTÊNCIA SOCIAL =====
    # Indicador 1: Bolsa Família
    bolsa_familia_total = (
        df.filter(pl.col("bolsa_familia_indicador") == True).height
        if "bolsa_familia_indicador" in df.columns
        else 0
    )
    bolsa_familia_perc = (
        (bolsa_familia_total / total_geral * 100) if total_geral > 0 else 0.0
    )

    # Indicador 2: CadÚnico Atualizado
    cadunico_total = (
        df.filter(pl.col("cadunico_indicador") == True).height
        if "cadunico_indicador" in df.columns
        else 0
    )
    cadunico_perc = (cadunico_total / total_geral * 100) if total_geral > 0 else 0.0

    # Indicador 3: Completude Assistência (0 protocolos violados)
    assistencia_completude_total = (
        df.filter(pl.col("assistencia_protocolos_violados") == 0).height
        if "assistencia_protocolos_violados" in df.columns
        else 0
    )
    assistencia_completude_perc = (
        (assistencia_completude_total / total_geral * 100) if total_geral > 0 else 0.0
    )

    # ===== DIMENSÃO EDUCAÇÃO =====
    # Indicador 1: Frequência Adequada (>= 75%)
    frequencia_adequada_total = (
        df.filter(pl.col("frequencia_escolar_percentual") >= 75.0).height
        if "frequencia_escolar_percentual" in df.columns
        else 0
    )
    frequencia_adequada_perc = (
        (frequencia_adequada_total / total_geral * 100) if total_geral > 0 else 0.0
    )

    # Indicador 2: Completude Educação (0 protocolos violados)
    educacao_completude_total = (
        df.filter(pl.col("educacao_protocolos_violados") == 0).height
        if "educacao_protocolos_violados" in df.columns
        else 0
    )
    educacao_completude_perc = (
        (educacao_completude_total / total_geral * 100) if total_geral > 0 else 0.0
    )

    # ===== DIMENSÃO SAÚDE =====
    # Completude Saúde (0 protocolos violados)
    saude_completude_total = (
        df.filter(pl.col("saude_protocolos_violados") == 0).height
        if "saude_protocolos_violados" in df.columns
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
        total_protocolos_violados=int(total_violados) if total_violados else 0,
        percentual_protocolos_violados=perc_protocolos_violados,
        # Protocolos por dimensão
        total_protocolos_smas=int(total_smas) if total_smas else 0,
        total_protocolos_smas_violados=int(violados_smas) if violados_smas else 0,
        percentual_smas_violados=perc_smas_violados,
        total_protocolos_sme=int(total_sme) if total_sme else 0,
        total_protocolos_sme_violados=int(violados_sme) if violados_sme else 0,
        percentual_sme_violados=perc_sme_violados,
        total_protocolos_sms=int(total_sms) if total_sms else 0,
        total_protocolos_sms_violados=int(violados_sms) if violados_sms else 0,
        percentual_sms_violados=perc_sms_violados,
        # Dimensão Assistência Social
        assistencia_bolsa_familia_total=bolsa_familia_total,
        assistencia_bolsa_familia_percentual=bolsa_familia_perc,
        assistencia_cadunico_atualizado_total=cadunico_total,
        assistencia_cadunico_atualizado_percentual=cadunico_perc,
        assistencia_completude_total=assistencia_completude_total,
        assistencia_completude_percentual=assistencia_completude_perc,
        # Dimensão Educação
        educacao_frequencia_adequada_total=frequencia_adequada_total,
        educacao_frequencia_adequada_percentual=frequencia_adequada_perc,
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

    Usa cohort como proxy para meses. Para cada safra, calcula:
    - Completude geral (% com 0 protocolos violados)
    - Completude por dimensão (% com 0 protocolos violados em cada secretaria)

    Args:
        df: Polars DataFrame com dados de participantes

    Returns:
        Lista de pontos temporais com completude por dimensão
    """
    if df.is_empty() or "cohort" not in df.columns:
        return []

    resultado = []

    # Group by cohort
    df_tempo = df.with_columns(pl.col("cohort").cast(pl.Utf8).alias("mes"))
    cohorts = sorted(df_tempo["mes"].unique().to_list())

    for cohort in cohorts:
        if cohort is None:
            continue

        df_mes = df_tempo.filter(pl.col("mes") == cohort)
        total = len(df_mes)

        if total == 0:
            continue

        # Completude geral (0 protocolos violados no total)
        regulares = (
            df_mes.filter(pl.col("total_protocolos_violados") == 0).height
            if "total_protocolos_violados" in df_mes.columns
            else 0
        )
        completude_todos = (regulares / total * 100) if total > 0 else 0.0

        # Completude Saúde (0 protocolos violados em saúde)
        saude_ok = (
            df_mes.filter(pl.col("saude_protocolos_violados") == 0).height
            if "saude_protocolos_violados" in df_mes.columns
            else 0
        )
        completude_saude = (saude_ok / total * 100) if total > 0 else 0.0

        # Completude Educação (0 protocolos violados em educação)
        educacao_ok = (
            df_mes.filter(pl.col("educacao_protocolos_violados") == 0).height
            if "educacao_protocolos_violados" in df_mes.columns
            else 0
        )
        completude_educacao = (educacao_ok / total * 100) if total > 0 else 0.0

        # Completude Assistência (0 protocolos violados em assistência)
        assistencia_ok = (
            df_mes.filter(pl.col("assistencia_protocolos_violados") == 0).height
            if "assistencia_protocolos_violados" in df_mes.columns
            else 0
        )
        completude_assistencia = (assistencia_ok / total * 100) if total > 0 else 0.0

        resultado.append(
            ResultadoProgramaPoint(
                mes=cohort,
                todos=round(completude_todos, 1),
                saude=round(completude_saude, 1),
                educacao=round(completude_educacao, 1),
                assistencia=round(completude_assistencia, 1),
            )
        )

    return resultado
