"""
Dashboard API - Usando dados pré-agregados da tabela de dashboard.

Este módulo usa uma tabela com indicadores já calculados, permitindo
performance muito melhor e métricas mais precisas.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Any, Optional
import polars as pl
import json
import time

from src.core.security.jwt import verify_jwt, CurrentUserPermissions
from src.utils.log import logger
from src.api.v1.schemas import (
    Dashboard,
    PaginatedResponse,
)
from src.utils.data_manager import DataManager
from src.api.v1.queries import DASHBOARD_TABLE_QUERY

router = APIRouter(dependencies=[Depends(verify_jwt)], tags=["Dashboard"])

# Configuração de filter options para a tabela de dashboard
DASHBOARD_FILTER_OPTIONS_CONFIG = {
    "grupos": {"column": "pic_grupo"},
    "cohorts": {"column": "pic_cohort"},
    "status_list": {"column": "pic_status"},
    "bairros": {"column": "bairro"},
    "cres": {"column": "id_cre"},
    "aps": {"column": "id_ap"},
    "cas_list": {"column": "id_cas"},
}


@router.get(
    "/dashboard",
    summary="Métricas do Dashboard",
    response_model=PaginatedResponse[Dashboard],
)
async def get_dashboard_metrics(
    permissions: CurrentUserPermissions,
    # Filtros específicos do dashboard
    grupo: Optional[str] = Query(None, description="Filtrar por grupo (crianca, gestante)"),
    cohort: Optional[str] = Query(None, description="Filtrar por safra"),
    status: Optional[str] = Query(None, description="Filtrar por status (ativo, inativo)"),
    bairro: Optional[str] = Query(None, description="Filtrar por bairro"),
    cre: Optional[str] = Query(None, description="Filtrar por CRE"),
    ap: Optional[str] = Query(None, description="Filtrar por AP"),
    cas: Optional[str] = Query(None, description="Filtrar por CAS"),
    bypass_cache: bool = Query(False, description="Forçar refresh do cache"),
) -> Any:
    """
    Retorna métricas agregadas para o dashboard principal.

    Usa dados pré-agregados da tabela de dashboard para performance otimizada.
    """
    per = permissions.model_dump(exclude_none=True)
    per_log = {
        "cpf": per.get("cpf"),
        "is_admin": per.get("is_admin"),
        "is_super_admin": per.get("is_super_admin"),
    }

    # Construir dict de filtros (mapeando para colunas da tabela)
    filters_dict = {}
    if grupo:
        filters_dict["pic_grupo"] = grupo
    if cohort:
        filters_dict["pic_cohort"] = cohort
    if status:
        filters_dict["pic_status"] = status
    if bairro:
        filters_dict["bairro"] = bairro
    if cre:
        filters_dict["id_cre"] = cre
    if ap:
        filters_dict["id_ap"] = ap
    if cas:
        filters_dict["id_cas"] = cas

    logger.info("Fetching dashboard metrics from pre-aggregated table")
    logger.info(f"🔑 Permissions: {per_log}")
    logger.info(f"☰ Filters: {filters_dict}")

    try:
        start_time = time.perf_counter()

        # Usar fetch_filter_paginate para buscar dados com filtros e permissões aplicados
        df_filtered, meta, filter_options = DataManager.fetch_filter_paginate(
            query=DASHBOARD_TABLE_QUERY,
            filters_dict=filters_dict,
            page=1,
            page_size=None,  # Retorna todos os dados (sem paginação)
            filter_columns_config=DASHBOARD_FILTER_OPTIONS_CONFIG,
            user_permissions=permissions,
            bypass_cache=bypass_cache,
        )

        fetch_time = time.perf_counter() - start_time
        logger.info(f"⏱️ [TIMING] Data fetch + filter: {fetch_time:.3f}s ({len(df_filtered)} rows)")

        # Se vazio após filtros, retornar métricas zeradas
        if df_filtered.is_empty():
            empty_dashboard = _create_empty_dashboard()
            return PaginatedResponse(
                meta=meta,
                data=[empty_dashboard],
                filters=filter_options,
            )

        # Calcular métricas a partir dos dados pré-agregados
        metrics_start = time.perf_counter()
        dashboard_metrics = _calculate_dashboard_metrics(df_filtered)
        metrics_time = time.perf_counter() - metrics_start
        logger.info(f"⏱️ [TIMING] Metrics calculation: {metrics_time:.3f}s")

        total_time = time.perf_counter() - start_time
        logger.info(f"⏱️ [TIMING] Total dashboard request: {total_time:.3f}s")

        return PaginatedResponse(
            meta=meta,
            data=[dashboard_metrics],
            filters=filter_options,
        )

    except Exception as e:
        logger.error(f"❌ Error fetching dashboard metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _parse_json_column(value: Any) -> Any:
    """Parseia uma coluna JSON string para objeto Python."""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return None
    return value


def _calculate_dashboard_metrics(df: pl.DataFrame) -> Dashboard:
    """
    Calcula métricas do dashboard a partir de dados pré-agregados.

    ETAPA 1: Indicadores Principais
    - Total de participantes
    - % Regular
    - % Irregular
    - Completude por dimensão (Assistência, Educação, Saúde)
    """
    # === INDICADORES DE PARTICIPANTES ===
    participantes_regular_num = 0
    participantes_regular_den = 0
    participantes_irregular_num = 0
    participantes_irregular_den = 0

    # === PROTOCOLOS POR SECRETARIA (para completude) ===
    protocolos_smas = {"num": 0, "den": 0}
    protocolos_sme = {"num": 0, "den": 0}
    protocolos_sms = {"num": 0, "den": 0}

    # Processar cada linha
    for row in df.to_dicts():
        # Parsear indicador de participantes regular
        ind_regular = _parse_json_column(row.get("indicador_participantes_percentual_regular"))
        if ind_regular:
            if isinstance(ind_regular, list):
                ind_regular = ind_regular[0] if ind_regular else {}
            if isinstance(ind_regular, dict):
                participantes_regular_num += ind_regular.get("numerador", 0) or 0
                participantes_regular_den += ind_regular.get("denominador", 0) or 0

        # Parsear indicador de participantes irregular
        ind_irregular = _parse_json_column(row.get("indicador_participantes_percentual_irregular"))
        if ind_irregular:
            if isinstance(ind_irregular, list):
                ind_irregular = ind_irregular[0] if ind_irregular else {}
            if isinstance(ind_irregular, dict):
                participantes_irregular_num += ind_irregular.get("numerador", 0) or 0
                participantes_irregular_den += ind_irregular.get("denominador", 0) or 0

        # Processar protocolos para completude por dimensão
        protocolos = _parse_json_column(row.get("indicador_protocolos_percentual_regular"))
        if protocolos:
            if not isinstance(protocolos, list):
                protocolos = [protocolos] if protocolos else []

            for protocolo in protocolos:
                if not isinstance(protocolo, dict):
                    continue

                secretaria = protocolo.get("protocolo_secretaria", "")
                valor_recente = protocolo.get("valor_mais_recente") or {}

                if isinstance(valor_recente, list):
                    valor_recente = valor_recente[0] if valor_recente else {}
                if not isinstance(valor_recente, dict):
                    valor_recente = {}

                numerador = valor_recente.get("indicador_numerador", 0) or 0
                denominador = valor_recente.get("indicador_denominador", 0) or 0

                if secretaria == "SMAS":
                    protocolos_smas["num"] += numerador
                    protocolos_smas["den"] += denominador
                elif secretaria == "SME":
                    protocolos_sme["num"] += numerador
                    protocolos_sme["den"] += denominador
                elif secretaria == "SMS":
                    protocolos_sms["num"] += numerador
                    protocolos_sms["den"] += denominador

    # Calcular percentuais
    total_participantes = participantes_regular_den  # Denominador é o total
    perc_regular = (participantes_regular_num / participantes_regular_den * 100) if participantes_regular_den > 0 else 0.0
    perc_irregular = (participantes_irregular_num / participantes_irregular_den * 100) if participantes_irregular_den > 0 else 0.0

    # Completude por dimensão
    def calc_perc(data: dict) -> float:
        if data["den"] > 0:
            return round((data["num"] / data["den"]) * 100, 1)
        return 0.0

    assistencia_completude = calc_perc(protocolos_smas)
    educacao_completude = calc_perc(protocolos_sme)
    saude_completude = calc_perc(protocolos_sms)

    return Dashboard(
        # Totais básicos
        total_participantes_ativos=total_participantes,
        total_participantes_inativos=0,
        total_participantes_geral=total_participantes,
        # Métricas principais
        total_participantes_regulares=participantes_regular_num,
        total_participantes_irregulares=participantes_irregular_num,
        percentual_regular=round(perc_regular, 1),
        percentual_irregular=round(perc_irregular, 1),
        # Atenção (não disponível na nova tabela)
        total_participantes_em_atencao=0,
        percentual_em_atencao=0.0,
        # Protocolos (vazio por enquanto)
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
        # Dimensão Assistência Social
        assistencia_completude_total=protocolos_smas["num"],
        assistencia_completude_percentual=assistencia_completude,
        # Dimensão Educação
        educacao_completude_total=protocolos_sme["num"],
        educacao_completude_percentual=educacao_completude,
        # Dimensão Saúde
        saude_completude_total=protocolos_sms["num"],
        saude_completude_percentual=saude_completude,
        # Distribuições (vazio por enquanto)
        distribuicao_por_grupo=[],
        top_bairros=[],
        distribuicao_motivo_saida=[],
        distribuicao_por_safra=[],
        resultado_programa=[],
    )


def _create_empty_dashboard() -> Dashboard:
    """Cria um dashboard vazio com todas as métricas zeradas."""
    return Dashboard(
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
        resultado_programa=[],
    )
