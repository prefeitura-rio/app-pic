"""
Dashboard API - Usando dados pré-agregados da tabela de dashboard.

Este módulo usa uma tabela com indicadores já calculados, permitindo
performance muito melhor e métricas mais precisas.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Any, Optional, Dict, List
from collections import defaultdict
import polars as pl
import time

from src.core.security.jwt import verify_jwt, CurrentUserPermissions
from src.utils.log import logger
from src.api.v1.schemas import (
    Dashboard,
    ProtocoloIndicador,
    ResultadoProgramaPoint,
    DistribuicaoSafra,
    DistribuicaoMotivoSaida,
    DistribuicaoTempoIrregularidade,
    TempoMedioIrregularidade,
    TaxaResolucaoMensalPoint,
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
    "subprefeituras": {"column": "subprefeitura"},
    "regioes_administrativas": {"column": "regiao_administrativa"},
    "bairros": {"column": "bairro"},
    "cres": {"column": "id_cre", "label_column": "nome_cre"},
    "aps": {"column": "id_ap", "label_column": "nome_ap"},
    "cas_list": {"column": "id_cas", "label_column": "nome_cas"},
    "cras": {"column": "id_cras", "label_column": "nome_cras"},
    "escolas": {"column": "id_escola", "label_column": "nome_escola"},
    "clinicas": {"column": "id_clinica_familia", "label_column": "nome_clinica_familia"},
    "equipes_familia": {"column": "id_equipe_familia", "label_column": "nome_equipe_familia"},
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
    secretaria: Optional[str] = Query(None, description="Filtrar métricas por secretaria (SMAS, SME, SMS) - filtra gráficos, não dados"),
    subprefeitura: Optional[str] = Query(None, description="Filtrar por subprefeitura(s) - pode ser string separada por vírgula"),
    regiao_administrativa: Optional[str] = Query(None, description="Filtrar por região administrativa(s) - pode ser string separada por vírgula"),
    bairro: Optional[str] = Query(None, description="Filtrar por bairro(s) - pode ser string separada por vírgula"),
    cre: Optional[str] = Query(None, description="Filtrar por CRE"),
    ap: Optional[str] = Query(None, description="Filtrar por AP"),
    cas: Optional[str] = Query(None, description="Filtrar por CAS"),
    cras: Optional[str] = Query(None, description="Filtrar por CRAS"),
    escola: Optional[str] = Query(None, description="Filtrar por escola"),
    unidade_saude: Optional[str] = Query(None, description="Filtrar por unidade de saúde"),
    equipe_saude: Optional[str] = Query(None, description="Filtrar por equipe de saúde"),
    has_bolsa_familia: Optional[bool] = Query(None, description="Filtrar por beneficiários do Bolsa Família"),
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
    # Todos os filtros suportam multi-select (comma-separated)
    filters_dict = {}

    # Helper para parse de multi-select
    def parse_multi_select(value: Optional[str]) -> Optional[str | list[str]]:
        if not value:
            return None
        if "," in value:
            return [v.strip() for v in value.split(",") if v.strip()]
        return value

    if grupo:
        filters_dict["pic_grupo"] = parse_multi_select(grupo)
    if cohort:
        filters_dict["pic_cohort"] = parse_multi_select(cohort)
    if status:
        filters_dict["pic_status"] = parse_multi_select(status)
    if subprefeitura:
        filters_dict["subprefeitura"] = parse_multi_select(subprefeitura)
    if regiao_administrativa:
        filters_dict["regiao_administrativa"] = parse_multi_select(regiao_administrativa)
    if bairro:
        filters_dict["bairro"] = parse_multi_select(bairro)
    if cre:
        filters_dict["id_cre"] = parse_multi_select(cre)
    if ap:
        filters_dict["id_ap"] = parse_multi_select(ap)
    if cas:
        filters_dict["id_cas"] = parse_multi_select(cas)
    if cras:
        filters_dict["id_cras"] = parse_multi_select(cras)
    if escola:
        filters_dict["id_escola"] = parse_multi_select(escola)
    if unidade_saude:
        filters_dict["id_clinica_familia"] = parse_multi_select(unidade_saude)
    if equipe_saude:
        filters_dict["id_equipe_familia"] = parse_multi_select(equipe_saude)
    if has_bolsa_familia is not None:
        filters_dict["has_bolsa_familia"] = has_bolsa_familia

    logger.info("Fetching dashboard metrics from pre-aggregated table")
    logger.info(f"🔑 Permissions: {per_log}")
    logger.info(f"☰ Filters: {filters_dict}")

    # Dashboard só para admin TODOS (dados pré-agregados não podem ser filtrados por secretaria)
    # Bloquear para secretarias específicas (SME, SMS, SMAS) e para NULL (sem acesso)
    if permissions and permissions.secretaria_acesso != "TODOS":
        logger.warning(f"⚠️ Dashboard não disponível para secretaria_acesso: {permissions.secretaria_acesso}. Retornando vazio.")
        empty_dashboard = _create_empty_dashboard()
        from src.api.v1.schemas import PaginationMeta
        return PaginatedResponse(
            meta=PaginationMeta(
                page=1,
                page_size=0,
                total_rows=0,
                total_pages=0,
                cache_hit=False,
                can_view_dashboard=False,  # Backend indica que usuário não pode ver dashboard
            ),
            data=[empty_dashboard],
            filters={},
        )

    try:
        start_time = time.perf_counter()

        # Usar fetch_filter_paginate para buscar dados com filtros e permissões aplicados
        df_filtered, meta, filter_options = await DataManager.fetch_filter_paginate(
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
            # Adicionar flag indicando que usuário pode ver dashboard
            meta_with_flag = meta.model_copy(update={"can_view_dashboard": True})
            return PaginatedResponse(
                meta=meta_with_flag,
                data=[empty_dashboard],
                filters=filter_options,
            )

        # Calcular métricas a partir dos dados pré-agregados
        # Passar filtro de secretaria para filtrar gráficos (não dados)
        metrics_start = time.perf_counter()
        dashboard_metrics = _calculate_dashboard_metrics(df_filtered, filtro_secretaria=secretaria)
        metrics_time = time.perf_counter() - metrics_start
        logger.info(f"⏱️ [TIMING] Metrics calculation: {metrics_time:.3f}s")

        total_time = time.perf_counter() - start_time
        logger.info(f"⏱️ [TIMING] Total dashboard request: {total_time:.3f}s")

        # Adicionar flag indicando que usuário pode ver dashboard
        meta_with_flag = meta.model_copy(update={"can_view_dashboard": True})
        return PaginatedResponse(
            meta=meta_with_flag,
            data=[dashboard_metrics],
            filters=filter_options,
        )

    except Exception as e:
        logger.error(f"❌ Error fetching dashboard metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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


def _calculate_dashboard_metrics(df: pl.DataFrame, filtro_secretaria: Optional[str] = None) -> Dashboard:
    """
    Calcula métricas do dashboard a partir de dados pré-agregados do BigQuery.

    VERSÃO OTIMIZADA V2: Usa operações 100% vetorizadas do Polars.
    Os dados já vêm como Struct/List nativos do Polars (não precisa parsear JSON).

    PROCESSAMENTO:
    1. Indicadores Principais: struct.field().sum() direto
    2. Protocolos Individuais: explode + struct.field + group_by
    3. Resultado do Programa: struct.field para cada secretaria
    4. Distribuição por Safra: group_by nativo
    5. Motivos de Saída: group_by nativo
    6. Tempo de Irregularidade: explode + struct.field + agregações
    7. Taxa de Resolução Mensal: explode + struct.field + group_by
    """
    import time as perf_time

    # =========================================================================
    # SEÇÃO 4 + 5: SAFRAS E MOTIVOS (Polars nativo - instantâneo)
    # =========================================================================
    section_start = perf_time.perf_counter()

    # Preparar coluna de quantidade (com fallback para 1)
    df_with_qtd = df.with_columns([
        pl.col("indicador_participantes_qtd_total").cast(pl.Int64).fill_null(1).alias("qtd"),
        pl.col("pic_status").fill_null("").str.to_lowercase().alias("status_lower"),
        pl.col("pic_cohort").cast(pl.Utf8).str.slice(0, 7).alias("cohort_str"),
    ])

    # 4. Distribuição por Safra - group_by nativo
    safra_df = (
        df_with_qtd
        .filter(pl.col("cohort_str").is_not_null() & (pl.col("cohort_str") != ""))
        .group_by("cohort_str", "status_lower")
        .agg(pl.col("qtd").sum().alias("total"))
    )

    safras_agregadas: Dict[str, Dict[str, int]] = defaultdict(lambda: {"ativos": 0, "inativos": 0})
    for row in safra_df.iter_rows(named=True):
        cohort = row["cohort_str"]
        status = row["status_lower"]
        total = row["total"] or 0
        if status == "ativo":
            safras_agregadas[cohort]["ativos"] += total
        else:
            safras_agregadas[cohort]["inativos"] += total

    # 5. Motivos de Saída - group_by nativo
    motivos_df = (
        df_with_qtd
        .filter(pl.col("status_lower") == "inativo")
        .with_columns([
            pl.col("pic_status_inativo_motivo").fill_null("Não informado").alias("motivo")
        ])
        .group_by("motivo")
        .agg(pl.col("qtd").sum().alias("total"))
    )

    motivos_saida: Dict[str, int] = {}
    for row in motivos_df.iter_rows(named=True):
        motivo = row["motivo"] or "Não informado"
        motivos_saida[motivo.strip() if motivo.strip() else "Não informado"] = row["total"] or 0

    logger.info(f"⚡ Seções 4+5 (Safras+Motivos): {perf_time.perf_counter() - section_start:.3f}s")

    # =========================================================================
    # SEÇÃO 1: INDICADORES PRINCIPAIS (Polars struct.field - instantâneo)
    # =========================================================================
    section_start = perf_time.perf_counter()

    # Extrair numerador/denominador diretamente do Struct usando Polars nativo
    participantes_regular_num = df.select(
        pl.col("indicador_participantes_percentual_regular").struct.field("numerador").sum()
    ).item() or 0

    participantes_regular_den = df.select(
        pl.col("indicador_participantes_percentual_regular").struct.field("denominador").sum()
    ).item() or 0

    participantes_irregular_num = df.select(
        pl.col("indicador_participantes_percentual_irregular").struct.field("numerador").sum()
    ).item() or 0

    participantes_irregular_den = df.select(
        pl.col("indicador_participantes_percentual_irregular").struct.field("denominador").sum()
    ).item() or 0

    logger.info(f"⚡ Seção 1 (Indicadores): {perf_time.perf_counter() - section_start:.3f}s")

    # =========================================================================
    # SEÇÃO 2: PROTOCOLOS (explode + struct.field + group_by)
    # =========================================================================
    section_start = perf_time.perf_counter()

    # Explode a lista de protocolos e extrair campos
    protocolos_agregados: Dict[str, Dict[str, Any]] = {}

    if "indicador_protocolos_percentual_regular" in df.columns:
        df_protocolos = (
            df.select(pl.col("indicador_protocolos_percentual_regular"))
            .explode("indicador_protocolos_percentual_regular")
            .filter(pl.col("indicador_protocolos_percentual_regular").is_not_null())
        )

        if len(df_protocolos) > 0:
            # Extrair campos do struct
            df_protocolos = df_protocolos.with_columns([
                pl.col("indicador_protocolos_percentual_regular").struct.field("protocolo_id").alias("protocolo_id"),
                pl.col("indicador_protocolos_percentual_regular").struct.field("protocolo_descricao").alias("descricao"),
                pl.col("indicador_protocolos_percentual_regular").struct.field("protocolo_secretaria").alias("secretaria"),
                pl.col("indicador_protocolos_percentual_regular").struct.field("valor_mais_recente").alias("valor_recente"),
            ])

            # valor_mais_recente é uma List de Structs, pegar o primeiro elemento
            df_protocolos = df_protocolos.with_columns([
                pl.col("valor_recente").list.first().alias("valor_recente_first"),
            ])

            # Extrair numerador/denominador do primeiro elemento
            df_protocolos = df_protocolos.with_columns([
                pl.col("valor_recente_first").struct.field("indicador_numerador").alias("num"),
                pl.col("valor_recente_first").struct.field("indicador_denominador").alias("den"),
            ])

            # Agregar por protocolo_id
            df_agg = (
                df_protocolos
                .filter(pl.col("protocolo_id").is_not_null())
                .group_by("protocolo_id")
                .agg([
                    pl.col("descricao").first().alias("descricao"),
                    pl.col("secretaria").first().alias("secretaria"),
                    pl.col("num").sum().alias("num"),
                    pl.col("den").sum().alias("den"),
                ])
            )

            for row in df_agg.iter_rows(named=True):
                protocolos_agregados[row["protocolo_id"]] = {
                    "descricao": row["descricao"] or "",
                    "secretaria": row["secretaria"] or "",
                    "num": row["num"] or 0,
                    "den": row["den"] or 0,
                }

    logger.info(f"⚡ Seção 2 (Protocolos): {perf_time.perf_counter() - section_start:.3f}s")

    # =========================================================================
    # SEÇÃO 3: SÉRIE TEMPORAL (struct.field para cada secretaria)
    # =========================================================================
    section_start = perf_time.perf_counter()

    evolucao_mensal: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"num": 0, "den": 0})
    )

    if "serie_participantes_percentual_regular" in df.columns:
        for chave, nome_secretaria in [("geral", "TODOS"), ("smas", "SMAS"), ("sme", "SME"), ("sms", "SMS")]:
            try:
                df_serie = (
                    df.select(
                        pl.col("serie_participantes_percentual_regular").struct.field(chave).alias("pontos")
                    )
                    .explode("pontos")
                    .filter(pl.col("pontos").is_not_null())
                )

                if len(df_serie) > 0:
                    df_serie = df_serie.with_columns([
                        pl.col("pontos").struct.field("data_referencia_mensal").cast(pl.Utf8).str.slice(0, 7).alias("mes"),
                        pl.col("pontos").struct.field("indicador_numerador").alias("num"),
                        pl.col("pontos").struct.field("indicador_denominador").alias("den"),
                    ])

                    df_agg = df_serie.group_by("mes").agg([
                        pl.col("num").sum().alias("num"),
                        pl.col("den").sum().alias("den"),
                    ])

                    for row in df_agg.iter_rows(named=True):
                        if row["mes"]:
                            evolucao_mensal[row["mes"]][nome_secretaria]["num"] = row["num"] or 0
                            evolucao_mensal[row["mes"]][nome_secretaria]["den"] = row["den"] or 0
            except Exception:
                pass  # Secretaria pode não existir na estrutura

    logger.info(f"⚡ Seção 3 (Série Temporal): {perf_time.perf_counter() - section_start:.3f}s")

    # =========================================================================
    # SEÇÃO 6: TEMPO DE IRREGULARIDADE (explode + agregações)
    # =========================================================================
    section_start = perf_time.perf_counter()

    tempo_irregular_por_secretaria: Dict[str, List[int]] = defaultdict(list)

    if "indicador_tempo_irregular" in df.columns:
        df_tempo = (
            df.select(pl.col("indicador_tempo_irregular"))
            .explode("indicador_tempo_irregular")
            .filter(pl.col("indicador_tempo_irregular").is_not_null())
        )

        if len(df_tempo) > 0:
            df_tempo = df_tempo.with_columns([
                pl.col("indicador_tempo_irregular").struct.field("secretaria").str.to_lowercase().alias("secretaria"),
                pl.col("indicador_tempo_irregular").struct.field("valor_array").alias("valores"),
            ])

            # Explodir os valores individuais
            df_valores = (
                df_tempo
                .filter(pl.col("secretaria").is_not_null())
                .explode("valores")
                .filter(pl.col("valores").is_not_null() & (pl.col("valores") > 0))
            )

            if len(df_valores) > 0:
                # Coletar valores por secretaria
                for row in df_valores.select(["secretaria", "valores"]).iter_rows():
                    secretaria, valor = row
                    tempo_irregular_por_secretaria[secretaria].append(valor)
                    tempo_irregular_por_secretaria["geral"].append(valor)

    logger.info(f"⚡ Seção 6 (Tempo Irregularidade): {perf_time.perf_counter() - section_start:.3f}s")

    # =========================================================================
    # SEÇÃO 7: TAXA DE RESOLUÇÃO MENSAL (explode + group_by)
    # =========================================================================
    section_start = perf_time.perf_counter()

    resolucao_mensal: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"num": 0, "den": 0})
    )

    if "serie_resolucao_alertas_percentual" in df.columns:
        df_resolucao = (
            df.select(pl.col("serie_resolucao_alertas_percentual"))
            .explode("serie_resolucao_alertas_percentual")
            .filter(pl.col("serie_resolucao_alertas_percentual").is_not_null())
        )

        if len(df_resolucao) > 0:
            df_resolucao = df_resolucao.with_columns([
                pl.col("serie_resolucao_alertas_percentual").struct.field("secretaria").str.to_lowercase().alias("secretaria"),
                pl.col("serie_resolucao_alertas_percentual").struct.field("resultado_mensal").alias("resultado_mensal"),
            ])

            # Explodir resultado_mensal
            df_pontos = (
                df_resolucao
                .filter(pl.col("secretaria").is_not_null())
                .explode("resultado_mensal")
                .filter(pl.col("resultado_mensal").is_not_null())
            )

            if len(df_pontos) > 0:
                df_pontos = df_pontos.with_columns([
                    pl.col("resultado_mensal").struct.field("data_referencia_mensal").cast(pl.Utf8).str.slice(0, 7).alias("mes"),
                    pl.col("resultado_mensal").struct.field("indicador_numerador").alias("num"),
                    pl.col("resultado_mensal").struct.field("indicador_denominador").alias("den"),
                ])

                mapa_sec = {"smas": "SMAS", "sme": "SME", "sms": "SMS"}

                # Agregar por mes + secretaria
                df_agg = df_pontos.group_by(["mes", "secretaria"]).agg([
                    pl.col("num").sum().alias("num"),
                    pl.col("den").sum().alias("den"),
                ])

                for row in df_agg.iter_rows(named=True):
                    if row["mes"] and row["secretaria"]:
                        nome_sec = mapa_sec.get(row["secretaria"], row["secretaria"].upper())
                        resolucao_mensal[row["mes"]][nome_sec]["num"] += row["num"] or 0
                        resolucao_mensal[row["mes"]][nome_sec]["den"] += row["den"] or 0
                        resolucao_mensal[row["mes"]]["TODOS"]["num"] += row["num"] or 0
                        resolucao_mensal[row["mes"]]["TODOS"]["den"] += row["den"] or 0

    logger.info(f"⚡ Seção 7 (Taxa Resolução): {perf_time.perf_counter() - section_start:.3f}s")

    # =========================================================================
    # CALCULAR MÉTRICAS FINAIS
    # =========================================================================
    section_start = perf_time.perf_counter()

    # 1. Indicadores Principais
    total_participantes = participantes_regular_den
    total_regulares = participantes_regular_num
    total_irregulares = participantes_irregular_num
    perc_regular = (total_regulares / total_participantes * 100) if total_participantes > 0 else 0.0
    perc_irregular = (total_irregulares / total_participantes * 100) if total_participantes > 0 else 0.0

    # 2. Protocolos Individuais
    protocolos_lista: List[ProtocoloIndicador] = []
    for protocolo_id, dados in protocolos_agregados.items():
        num, den = dados["num"], dados["den"]
        perc_reg = (num / den * 100) if den > 0 else 0.0
        protocolos_lista.append(
            ProtocoloIndicador(
                protocolo_id=protocolo_id,
                protocolo_descricao=dados["descricao"],
                protocolo_secretaria=dados["secretaria"],
                numerador=num,
                denominador=den,
                percentual_regular=round(perc_reg, 1),
                percentual_irregular=round(100 - perc_reg, 1) if den > 0 else 0.0,
            )
        )
    protocolos_lista.sort(key=lambda p: (p.protocolo_secretaria, p.protocolo_descricao))

    # 3. Resultado do Programa
    resultado_programa: List[ResultadoProgramaPoint] = []
    for mes in sorted(evolucao_mensal.keys()):
        dados_mes = evolucao_mensal[mes]
        def calc_perc(sec: str) -> float:
            d = dados_mes.get(sec, {"num": 0, "den": 0})
            return round(d["num"] / d["den"] * 100, 1) if d["den"] > 0 else 0.0
        resultado_programa.append(
            ResultadoProgramaPoint(
                mes=mes, mes_label=_format_mes_label(mes),
                todos=calc_perc("TODOS"), saude=calc_perc("SMS"),
                educacao=calc_perc("SME"), assistencia=calc_perc("SMAS"),
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

    # 5. Motivos de Saída
    distribuicao_motivos: List[DistribuicaoMotivoSaida] = [
        DistribuicaoMotivoSaida(motivo=m, total=t)
        for m, t in sorted(motivos_saida.items(), key=lambda x: x[1], reverse=True)
    ]

    # 6. Tempo Médio de Irregularidade
    mapa_labels = {"geral": "Geral", "smas": "Assistência Social", "sme": "Educação", "sms": "Saúde"}
    tempo_medio_lista: List[TempoMedioIrregularidade] = []

    # Determinar quais secretarias incluir baseado no filtro
    if filtro_secretaria:
        # Normalizar filtro para lowercase (SMAS -> smas)
        filtro_norm = filtro_secretaria.lower()
        secretarias_incluir = ["geral", filtro_norm]
    else:
        secretarias_incluir = ["geral", "smas", "sme", "sms"]

    for secretaria in secretarias_incluir:
        valores = tempo_irregular_por_secretaria.get(secretaria, [])
        tempo_medio = sum(valores) / len(valores) if valores else 0.0
        tempo_medio_lista.append(
            TempoMedioIrregularidade(
                secretaria=secretaria,
                secretaria_label=mapa_labels.get(secretaria, secretaria.upper()),
                tempo_medio_dias=round(tempo_medio, 1),
                total_irregulares=len(valores),
            )
        )

    # 7. Distribuição por Tempo de Irregularidade (histograma)
    todos_valores = tempo_irregular_por_secretaria.get("geral", [])
    total_valores = len(todos_valores)
    faixas_config = [("0-30", "0-30 dias", 0, 30), ("31-60", "31-60 dias", 31, 60),
                     ("61-90", "61-90 dias", 61, 90), ("90+", "90+ dias", 91, float("inf"))]
    distribuicao_tempo: List[DistribuicaoTempoIrregularidade] = []
    for faixa, faixa_label, min_d, max_d in faixas_config:
        count = sum(1 for v in todos_valores if min_d <= v <= max_d)
        distribuicao_tempo.append(
            DistribuicaoTempoIrregularidade(
                faixa=faixa, faixa_label=faixa_label, count=count,
                percentual=round(count / total_valores * 100, 1) if total_valores > 0 else 0.0,
            )
        )

    # 8. Taxa de Resolução Mensal
    taxa_resolucao_lista: List[TaxaResolucaoMensalPoint] = []
    for mes in sorted(resolucao_mensal.keys()):
        dados_mes = resolucao_mensal[mes]
        def calc_res(sec: str) -> float:
            d = dados_mes.get(sec, {"num": 0, "den": 0})
            return round(d["num"] / d["den"] * 100, 1) if d["den"] > 0 else 0.0
        taxa_resolucao_lista.append(
            TaxaResolucaoMensalPoint(
                mes=mes, mes_label=_format_mes_label(mes),
                todos=calc_res("TODOS"), saude=calc_res("SMS"),
                educacao=calc_res("SME"), assistencia=calc_res("SMAS"),
            )
        )

    logger.info(f"⚡ Métricas finais: {perf_time.perf_counter() - section_start:.3f}s")

    return Dashboard(
        total_participantes=total_participantes,
        total_regulares=total_regulares,
        total_irregulares=total_irregulares,
        percentual_regular=round(perc_regular, 1),
        percentual_irregular=round(perc_irregular, 1),
        protocolos=protocolos_lista,
        resultado_programa=resultado_programa,
        distribuicao_por_safra=distribuicao_safra,
        distribuicao_motivo_saida=distribuicao_motivos,
        tempo_medio_irregularidade=tempo_medio_lista,
        distribuicao_tempo_irregularidade=distribuicao_tempo,
        taxa_resolucao_mensal=taxa_resolucao_lista,
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
        tempo_medio_irregularidade=[],
        distribuicao_tempo_irregularidade=[],
        taxa_resolucao_mensal=[],
    )
