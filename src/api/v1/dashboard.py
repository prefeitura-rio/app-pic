"""
Dashboard API - Usando dados pré-agregados da tabela de dashboard.

Este módulo usa uma tabela com indicadores já calculados, permitindo
performance muito melhor e métricas mais precisas.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Any, Optional, Dict, List
from collections import defaultdict
import polars as pl
import json
import time

from src.core.security.jwt import verify_jwt, CurrentUserPermissions
from src.utils.log import logger
from src.api.v1.schemas import (
    Dashboard,
    ProtocoloIndicador,
    ResultadoProgramaPoint,
    DistribuicaoSafra,
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

# Mapeamento de mês numérico para label
MESES_LABELS = {
    "01": "Jan", "02": "Fev", "03": "Mar", "04": "Abr",
    "05": "Mai", "06": "Jun", "07": "Jul", "08": "Ago",
    "09": "Set", "10": "Out", "11": "Nov", "12": "Dez",
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


def _safe_int(value: Any) -> int:
    """Converte valor para int de forma segura."""
    if value is None:
        return 0
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


def _format_mes_label(mes: str) -> str:
    """
    Converte "2025-12-01" ou "2025-12" para "Dez/25".
    """
    try:
        parts = mes.split("-")
        if len(parts) >= 2:
            ano = parts[0][2:]  # "2025" -> "25"
            mes_num = parts[1]  # "12"
            mes_nome = MESES_LABELS.get(mes_num, mes_num)
            return f"{mes_nome}/{ano}"
    except Exception:
        pass
    return mes


def _calculate_dashboard_metrics(df: pl.DataFrame) -> Dashboard:
    """
    Calcula métricas do dashboard a partir de dados pré-agregados do BigQuery.

    PROCESSAMENTO:
    1. Indicadores Principais: soma de numeradores/denominadores de participantes
    2. Protocolos Individuais: agregação por protocolo_id usando valor_mais_recente
    3. Resultado do Programa: usa serie_participantes_percentual_regular (já agregado por secretaria)
    4. Distribuição por Safra: agregação por cohort
    """
    # =========================================================================
    # SEÇÃO 1: INDICADORES PRINCIPAIS
    # =========================================================================
    participantes_regular_num = 0
    participantes_regular_den = 0
    participantes_irregular_num = 0
    participantes_irregular_den = 0

    # =========================================================================
    # SEÇÃO 2: PROTOCOLOS INDIVIDUAIS (cards)
    # Estrutura: {protocolo_id: {descricao, secretaria, num, den}}
    # =========================================================================
    protocolos_agregados: Dict[str, Dict[str, Any]] = {}

    # =========================================================================
    # SEÇÃO 3: RESULTADO DO PROGRAMA (evolução mensal)
    # Usa serie_participantes_percentual_regular com estrutura:
    # {geral: [{data, num, den}], smas: [...], sme: [...], sms: [...]}
    # Estrutura agregada: {mes: {secretaria: {num, den}}}
    # =========================================================================
    evolucao_mensal: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"num": 0, "den": 0})
    )

    # =========================================================================
    # SEÇÃO 4: DISTRIBUIÇÃO POR SAFRA
    # =========================================================================
    safras_agregadas: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"ativos": 0, "inativos": 0}
    )

    # Processar cada linha do DataFrame
    for row in df.to_dicts():
        # -----------------------------------------------------------------
        # 1. Indicadores de Participantes
        # -----------------------------------------------------------------
        ind_regular = _parse_json_column(row.get("indicador_participantes_percentual_regular"))
        if ind_regular:
            if isinstance(ind_regular, list):
                ind_regular = ind_regular[0] if ind_regular else {}
            if isinstance(ind_regular, dict):
                participantes_regular_num += _safe_int(ind_regular.get("numerador"))
                participantes_regular_den += _safe_int(ind_regular.get("denominador"))

        ind_irregular = _parse_json_column(row.get("indicador_participantes_percentual_irregular"))
        if ind_irregular:
            if isinstance(ind_irregular, list):
                ind_irregular = ind_irregular[0] if ind_irregular else {}
            if isinstance(ind_irregular, dict):
                participantes_irregular_num += _safe_int(ind_irregular.get("numerador"))
                participantes_irregular_den += _safe_int(ind_irregular.get("denominador"))

        # -----------------------------------------------------------------
        # 2. Processar Protocolos Individuais (cards)
        # -----------------------------------------------------------------
        protocolos = _parse_json_column(row.get("indicador_protocolos_percentual_regular"))
        if protocolos:
            if not isinstance(protocolos, list):
                protocolos = [protocolos]

            for protocolo in protocolos:
                if not isinstance(protocolo, dict):
                    continue

                protocolo_id = protocolo.get("protocolo_id", "")
                protocolo_descricao = protocolo.get("protocolo_descricao", "")
                protocolo_secretaria = protocolo.get("protocolo_secretaria", "")

                if not protocolo_id:
                    continue

                # Agregar valor_mais_recente para cards de protocolo
                valor_recente = protocolo.get("valor_mais_recente")
                if valor_recente:
                    if isinstance(valor_recente, list):
                        valor_recente = valor_recente[0] if valor_recente else {}
                    if isinstance(valor_recente, dict):
                        num = _safe_int(valor_recente.get("indicador_numerador"))
                        den = _safe_int(valor_recente.get("indicador_denominador"))

                        if protocolo_id not in protocolos_agregados:
                            protocolos_agregados[protocolo_id] = {
                                "descricao": protocolo_descricao,
                                "secretaria": protocolo_secretaria,
                                "num": 0,
                                "den": 0,
                            }

                        protocolos_agregados[protocolo_id]["num"] += num
                        protocolos_agregados[protocolo_id]["den"] += den

        # -----------------------------------------------------------------
        # 3. Processar Série Temporal (Resultado do Programa)
        # Usa serie_participantes_percentual_regular com estrutura:
        # {geral: [...], smas: [...], sme: [...], sms: [...]}
        # -----------------------------------------------------------------
        serie_temporal = _parse_json_column(row.get("serie_participantes_percentual_regular"))
        if serie_temporal and isinstance(serie_temporal, dict):
            # Mapeamento de chave da série para nome da secretaria
            mapa_secretarias = {
                "geral": "TODOS",
                "smas": "SMAS",
                "sme": "SME",
                "sms": "SMS",
            }

            for chave, nome_secretaria in mapa_secretarias.items():
                pontos = serie_temporal.get(chave)
                if not pontos:
                    continue

                if not isinstance(pontos, list):
                    pontos = [pontos]

                for ponto in pontos:
                    if not isinstance(ponto, dict):
                        continue

                    # Extrair mês (formato "2025-12-01" -> "2025-12")
                    data_ref = ponto.get("data_referencia_mensal")
                    if not data_ref:
                        continue

                    # Normalizar para "YYYY-MM"
                    if hasattr(data_ref, 'strftime'):
                        mes = data_ref.strftime("%Y-%m")
                    else:
                        data_ref_str = str(data_ref)
                        mes = data_ref_str[:7] if len(data_ref_str) >= 7 else data_ref_str

                    num = _safe_int(ponto.get("indicador_numerador"))
                    den = _safe_int(ponto.get("indicador_denominador"))

                    # Agregar por mês e secretaria
                    evolucao_mensal[mes][nome_secretaria]["num"] += num
                    evolucao_mensal[mes][nome_secretaria]["den"] += den

        # -----------------------------------------------------------------
        # 4. Distribuição por Safra
        # -----------------------------------------------------------------
        cohort = row.get("pic_cohort")
        status = row.get("pic_status", "")
        status_lower = status.lower() if isinstance(status, str) else ""
        qtd = _safe_int(row.get("indicador_participantes_qtd_total", 1))

        if cohort:
            # Converter cohort para string no formato YYYY-MM
            if hasattr(cohort, 'strftime'):
                # É um objeto date/datetime
                cohort_str = cohort.strftime("%Y-%m")
            else:
                # É uma string
                cohort_str = str(cohort)[:7]

            if status_lower == "ativo":
                safras_agregadas[cohort_str]["ativos"] += qtd
            else:
                safras_agregadas[cohort_str]["inativos"] += qtd

    # =========================================================================
    # CALCULAR MÉTRICAS FINAIS
    # =========================================================================

    # 1. Indicadores Principais
    total_participantes = participantes_regular_den
    total_regulares = participantes_regular_num
    total_irregulares = participantes_irregular_num

    perc_regular = (total_regulares / total_participantes * 100) if total_participantes > 0 else 0.0
    perc_irregular = (total_irregulares / total_participantes * 100) if total_participantes > 0 else 0.0

    # 2. Protocolos Individuais
    protocolos_lista: List[ProtocoloIndicador] = []
    for protocolo_id, dados in protocolos_agregados.items():
        num = dados["num"]
        den = dados["den"]
        perc_reg = (num / den * 100) if den > 0 else 0.0
        perc_irreg = 100 - perc_reg if den > 0 else 0.0

        protocolos_lista.append(
            ProtocoloIndicador(
                protocolo_id=protocolo_id,
                protocolo_descricao=dados["descricao"],
                protocolo_secretaria=dados["secretaria"],
                numerador=num,
                denominador=den,
                percentual_regular=round(perc_reg, 1),
                percentual_irregular=round(perc_irreg, 1),
            )
        )

    # Ordenar protocolos por secretaria e depois por descrição
    protocolos_lista.sort(key=lambda p: (p.protocolo_secretaria, p.protocolo_descricao))

    # 3. Resultado do Programa (evolução mensal)
    resultado_programa: List[ResultadoProgramaPoint] = []
    for mes in sorted(evolucao_mensal.keys()):
        dados_mes = evolucao_mensal[mes]

        # Calcular percentual por secretaria
        def calc_perc(secretaria: str) -> float:
            dados = dados_mes.get(secretaria, {"num": 0, "den": 0})
            if dados["den"] > 0:
                return round(dados["num"] / dados["den"] * 100, 1)
            return 0.0

        resultado_programa.append(
            ResultadoProgramaPoint(
                mes=mes,
                mes_label=_format_mes_label(mes),
                todos=calc_perc("TODOS"),
                saude=calc_perc("SMS"),
                educacao=calc_perc("SME"),
                assistencia=calc_perc("SMAS"),
            )
        )

    # 4. Distribuição por Safra
    distribuicao_safra: List[DistribuicaoSafra] = []
    for safra in sorted(safras_agregadas.keys()):
        dados = safras_agregadas[safra]
        distribuicao_safra.append(
            DistribuicaoSafra(
                safra=_format_mes_label(safra),
                total_participantes=dados["ativos"] + dados["inativos"],
                total_ativos=dados["ativos"],
                total_inativos=dados["inativos"],
            )
        )

    return Dashboard(
        # Indicadores Principais
        total_participantes=total_participantes,
        total_regulares=total_regulares,
        total_irregulares=total_irregulares,
        percentual_regular=round(perc_regular, 1),
        percentual_irregular=round(perc_irregular, 1),
        # Protocolos Individuais
        protocolos=protocolos_lista,
        # Evolução Mensal
        resultado_programa=resultado_programa,
        # Distribuição por Safra
        distribuicao_por_safra=distribuicao_safra,
        # Motivos de Saída (não disponível ainda)
        distribuicao_motivo_saida=[],
    )


def _create_empty_dashboard() -> Dashboard:
    """Cria um dashboard vazio com todas as métricas zeradas."""
    return Dashboard(
        total_participantes=0,
        total_regulares=0,
        total_irregulares=0,
        percentual_regular=0.0,
        percentual_irregular=0.0,
        protocolos=[],
        resultado_programa=[],
        distribuicao_por_safra=[],
        distribuicao_motivo_saida=[],
    )
