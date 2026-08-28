from collections import defaultdict
from typing import Any

import polars as pl

from src.pic.domain.models.dashboard import (
    Dashboard,
    DistribuicaoMotivoSaida,
    DistribuicaoSafra,
    DistribuicaoTempoIrregularidade,
    ProtocoloIndicador,
    ResultadoProgramaPoint,
    TaxaResolucaoMensalPoint,
    TempoMedioIrregularidade,
)
from src.pic.infrastructure.dashboard.formatting import _format_mes_label
from src.utils.log import logger

# ---------------------------------------------------------------------------
# Helpers shared by both compute paths
# ---------------------------------------------------------------------------

_MAPA_SECRETARIA_LABEL: dict[str, str] = {
    "geral": "Geral",
    "smas": "Assistência Social",
    "sme": "Educação",
    "sms": "Saúde",
}

_FAIXAS_TEMPO: list[tuple[str, str, float, float]] = [
    ("0-30",  "0-30 dias",  0.0,  30.0),
    ("31-60", "31-60 dias", 31.0, 60.0),
    ("61-90", "61-90 dias", 61.0, 90.0),
    ("90+",   "90+ dias",   91.0, float("inf")),
]


def _percentual(num: int | float, den: int | float) -> float:
    """round(num/den*100, 1) when den > 0, else 0.0."""
    if not den or den <= 0:
        return 0.0
    return round(num / den * 100, 1)


# ---------------------------------------------------------------------------
# PostgREST compute path (no Polars)
# ---------------------------------------------------------------------------


def _calculate_dashboard_metrics_postgrest(
    consolidado: dict[str, Any],
    protocolos: list[dict[str, Any]],
    series: list[dict[str, Any]],
    tempo: dict[str, Any],
    resolucao: list[dict[str, Any]],
    filtro_secretaria: str | None = None,
) -> Dashboard:
    """Compute all seven dashboard sections from PostgREST-fetched data.

    All inputs are plain Python dicts/lists — no Polars, no BigQuery structs.
    The same quirks as the V1 Polars path are preserved exactly.

    Args:
        consolidado: Output of ``_fetch_consolidado``:
            {"totals": {regular_num, regular_den, irregular_num},
             "safras": [{cohort, status, qtd}],
             "motivos": [{motivo, qtd}]}
        protocolos: Output of ``_fetch_protocolos``:
            [{protocolo_id, protocolo_descricao, protocolo_secretaria,
              numerador, denominador}]
        series: Output of ``_fetch_series``:
            [{serie_tipo, mes, numerador, denominador}]
        tempo: Output of ``_fetch_tempo``:
            {smas: {soma_duracao, quantidade},
             sme:  {soma_duracao, quantidade},
             sms:  {soma_duracao, quantidade}}
        resolucao: Output of ``_fetch_resolucao``:
            [{secretaria, mes, numerador, denominador}]
        filtro_secretaria: Optional secretaria param (SMS|SME|SMAS). Affects
            only which bands appear in section 6 (tempo médio).

    Returns:
        Fully populated ``Dashboard`` domain object.
    """
    import time as perf_time
    t0 = perf_time.perf_counter()

    # =========================================================================
    # SECTION 1 — Indicadores principais
    # =========================================================================
    totals = consolidado.get("totals", {})
    total_participantes: int = totals.get("regular_den", 0) or 0  # QUIRK 1
    total_regulares: int = totals.get("regular_num", 0) or 0
    total_irregulares: int = totals.get("irregular_num", 0) or 0
    percentual_regular = _percentual(total_regulares, total_participantes)
    percentual_irregular = _percentual(total_irregulares, total_participantes)

    logger.info(f"⚡ [postgrest] Seção 1: {perf_time.perf_counter() - t0:.3f}s")

    # =========================================================================
    # SECTION 2 — Protocolos
    # =========================================================================
    t1 = perf_time.perf_counter()

    # Aggregate by protocolo_id (rows may repeat across filter dimensions)
    proto_agg: dict[str, dict[str, Any]] = {}
    for row in protocolos:
        pid = row.get("protocolo_id")
        if not pid:
            continue
        if pid not in proto_agg:
            proto_agg[pid] = {
                "descricao": row.get("protocolo_descricao") or "",
                "secretaria": row.get("protocolo_secretaria") or "",
                "num": 0,
                "den": 0,
            }
        else:
            # First non-null wins for labels
            if not proto_agg[pid]["descricao"] and row.get("protocolo_descricao"):
                proto_agg[pid]["descricao"] = row["protocolo_descricao"]
            if not proto_agg[pid]["secretaria"] and row.get("protocolo_secretaria"):
                proto_agg[pid]["secretaria"] = row["protocolo_secretaria"]
        proto_agg[pid]["num"] += row.get("numerador") or 0
        proto_agg[pid]["den"] += row.get("denominador") or 0

    protocolos_lista: list[ProtocoloIndicador] = []
    for pid, dados in proto_agg.items():
        num, den = dados["num"], dados["den"]
        perc_reg_raw = (num / den * 100) if den > 0 else 0.0
        # QUIRK 2: complement computed on the unrounded value
        protocolos_lista.append(
            ProtocoloIndicador(
                protocolo_id=pid,
                protocolo_descricao=dados["descricao"],
                protocolo_secretaria=dados["secretaria"],
                numerador=num,
                denominador=den,
                percentual_regular=round(perc_reg_raw, 1),
                percentual_irregular=round(100 - perc_reg_raw, 1) if den > 0 else 0.0,
            )
        )
    protocolos_lista.sort(key=lambda p: (p.protocolo_secretaria, p.protocolo_descricao))

    logger.info(f"⚡ [postgrest] Seção 2: {perf_time.perf_counter() - t1:.3f}s")

    # =========================================================================
    # SECTION 3 — Resultado do programa (série mensal)
    # =========================================================================
    t1 = perf_time.perf_counter()

    _MAPA_SERIE: dict[str, str] = {
        "geral": "TODOS",
        "smas": "SMAS",
        "sme": "SME",
        "sms": "SMS",
    }

    evolucao: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"num": 0, "den": 0})
    )
    for row in series:
        tipo = (row.get("serie_tipo") or "").lower()
        nome_sec = _MAPA_SERIE.get(tipo)
        mes = row.get("mes")
        if not nome_sec or not mes:
            continue
        evolucao[mes][nome_sec]["num"] += row.get("numerador") or 0
        evolucao[mes][nome_sec]["den"] += row.get("denominador") or 0

    resultado_programa: list[ResultadoProgramaPoint] = []
    for mes in sorted(evolucao.keys()):
        d = evolucao[mes]
        resultado_programa.append(
            ResultadoProgramaPoint(
                mes=mes,
                mes_label=_format_mes_label(mes),
                todos=_percentual(d["TODOS"]["num"], d["TODOS"]["den"]),
                saude=_percentual(d["SMS"]["num"], d["SMS"]["den"]),
                educacao=_percentual(d["SME"]["num"], d["SME"]["den"]),
                assistencia=_percentual(d["SMAS"]["num"], d["SMAS"]["den"]),
            )
        )

    logger.info(f"⚡ [postgrest] Seção 3: {perf_time.perf_counter() - t1:.3f}s")

    # =========================================================================
    # SECTION 4 — Distribuição por safra
    # =========================================================================
    t1 = perf_time.perf_counter()

    safras_agg: dict[str, dict[str, int]] = defaultdict(
        lambda: {"ativos": 0, "inativos": 0}
    )
    for row in consolidado.get("safras", []):
        cohort = row.get("cohort")
        if not cohort:
            continue
        cohort_str = str(cohort)[:7]  # YYYY-MM
        if not cohort_str:
            continue
        status = (row.get("status") or "").lower()
        # QUIRK 3: qtd_total NULL → 1
        qtd: int = int(row.get("qtd") or 0) or 1
        if status == "ativo":
            safras_agg[cohort_str]["ativos"] += qtd
        else:
            safras_agg[cohort_str]["inativos"] += qtd

    distribuicao_safra: list[DistribuicaoSafra] = []
    for safra in sorted(safras_agg.keys()):
        d = safras_agg[safra]
        distribuicao_safra.append(
            DistribuicaoSafra(
                safra=_format_mes_label(safra),
                total_participantes=d["ativos"] + d["inativos"],
                total_ativos=d["ativos"],
                total_inativos=d["inativos"],
            )
        )

    logger.info(f"⚡ [postgrest] Seção 4: {perf_time.perf_counter() - t1:.3f}s")

    # =========================================================================
    # SECTION 5 — Distribuição por motivo de saída
    # =========================================================================
    t1 = perf_time.perf_counter()

    motivos_agg: dict[str, int] = defaultdict(int)
    for row in consolidado.get("motivos", []):
        motivo = row.get("motivo")
        # QUIRK 4: NULL or blank → "Não informado"
        if not motivo or not str(motivo).strip():
            motivo = "Não informado"
        else:
            motivo = str(motivo).strip()
        # QUIRK 3: qtd NULL → 1
        qtd = int(row.get("qtd") or 0) or 1
        motivos_agg[motivo] += qtd

    distribuicao_motivos: list[DistribuicaoMotivoSaida] = [
        DistribuicaoMotivoSaida(motivo=m, total=t)
        for m, t in sorted(motivos_agg.items(), key=lambda x: -x[1])
    ]

    logger.info(f"⚡ [postgrest] Seção 5: {perf_time.perf_counter() - t1:.3f}s")

    # =========================================================================
    # SECTION 6 — Tempo de irregularidade
    # =========================================================================
    t1 = perf_time.perf_counter()

    # QUIRK 5: "geral" is a virtual key = union of all secretarias
    tempo_por_sec: dict[str, dict[str, float | int]] = {
        "geral": {"soma": 0.0, "quantidade": 0},
        "smas":  {"soma": 0.0, "quantidade": 0},
        "sme":   {"soma": 0.0, "quantidade": 0},
        "sms":   {"soma": 0.0, "quantidade": 0},
    }
    for sec in ("smas", "sme", "sms"):
        sec_data = tempo.get(sec, {})
        soma = sec_data.get("soma_duracao") or 0.0
        qtd = int(sec_data.get("quantidade") or 0)
        tempo_por_sec[sec]["soma"] = soma
        tempo_por_sec[sec]["quantidade"] = qtd
        # Accumulate into "geral"
        tempo_por_sec["geral"]["soma"] += soma          # type: ignore[operator]
        tempo_por_sec["geral"]["quantidade"] += qtd     # type: ignore[operator]

    # QUIRK 6: filtro_secretaria restricts which bands appear, never filters rows
    if filtro_secretaria:
        secretarias_incluir = ["geral", filtro_secretaria.lower()]
    else:
        secretarias_incluir = ["geral", "smas", "sme", "sms"]

    tempo_medio_lista: list[TempoMedioIrregularidade] = []
    for sec in secretarias_incluir:
        d = tempo_por_sec.get(sec, {"soma": 0.0, "quantidade": 0})
        soma = d["soma"]
        qtd = d["quantidade"]
        media = round(soma / qtd, 1) if qtd > 0 else 0.0
        tempo_medio_lista.append(
            TempoMedioIrregularidade(
                secretaria=sec,
                secretaria_label=_MAPA_SECRETARIA_LABEL.get(sec, sec.upper()),
                tempo_medio_dias=media,
                total_irregulares=int(qtd),
            )
        )

    # Histograma MVP: a média de cada secretaria determina sua faixa e a
    # quantidade total daquela secretaria é alocada nessa faixa.
    # TODO: substituir por histograma real quando dados brutos estiverem
    # disponíveis em endpoint_participante_visao_geral_tempo_irregular_valores_brutos
    faixa_counts: dict[str, int] = {"0-30": 0, "31-60": 0, "61-90": 0, "90+": 0}
    total_geral = int(tempo_por_sec["geral"]["quantidade"])

    for sec in ("smas", "sme", "sms"):
        d = tempo_por_sec[sec]
        qtd = int(d["quantidade"])
        if qtd == 0:
            continue
        media_sec = d["soma"] / qtd  # type: ignore[operator]
        for faixa_key, _, min_d, max_d in _FAIXAS_TEMPO:
            if min_d <= media_sec <= max_d:
                faixa_counts[faixa_key] += qtd
                break

    distribuicao_tempo: list[DistribuicaoTempoIrregularidade] = []
    for faixa_key, faixa_label, _, _ in _FAIXAS_TEMPO:
        count = faixa_counts[faixa_key]
        distribuicao_tempo.append(
            DistribuicaoTempoIrregularidade(
                faixa=faixa_key,
                faixa_label=faixa_label,
                count=count,
                percentual=round(count / total_geral * 100, 1) if total_geral > 0 else 0.0,
            )
        )

    logger.info(f"⚡ [postgrest] Seção 6: {perf_time.perf_counter() - t1:.3f}s")

    # =========================================================================
    # SECTION 7 — Taxa de resolução mensal
    # =========================================================================
    t1 = perf_time.perf_counter()

    _MAPA_RESOLUCAO: dict[str, str] = {"smas": "SMAS", "sme": "SME", "sms": "SMS"}

    resolucao_agg: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"num": 0, "den": 0})
    )
    for row in resolucao:
        sec_raw = (row.get("secretaria") or "").lower()
        mes = row.get("mes")
        if not sec_raw or not mes:
            continue
        nome_sec = _MAPA_RESOLUCAO.get(sec_raw, sec_raw.upper())
        num = row.get("numerador") or 0
        den = row.get("denominador") or 0
        resolucao_agg[mes][nome_sec]["num"] += num
        resolucao_agg[mes][nome_sec]["den"] += den
        # QUIRK 7: TODOS accumulates every secretaria (including "GERAL")
        resolucao_agg[mes]["TODOS"]["num"] += num
        resolucao_agg[mes]["TODOS"]["den"] += den

    taxa_resolucao: list[TaxaResolucaoMensalPoint] = []
    for mes in sorted(resolucao_agg.keys()):
        d = resolucao_agg[mes]
        taxa_resolucao.append(
            TaxaResolucaoMensalPoint(
                mes=mes,
                mes_label=_format_mes_label(mes),
                todos=_percentual(d["TODOS"]["num"], d["TODOS"]["den"]),
                saude=_percentual(d["SMS"]["num"], d["SMS"]["den"]),
                educacao=_percentual(d["SME"]["num"], d["SME"]["den"]),
                assistencia=_percentual(d["SMAS"]["num"], d["SMAS"]["den"]),
            )
        )

    logger.info(f"⚡ [postgrest] Seção 7: {perf_time.perf_counter() - t1:.3f}s")
    logger.info(f"⚡ [postgrest] total compute: {perf_time.perf_counter() - t0:.3f}s")

    return Dashboard(
        total_participantes=total_participantes,
        total_regulares=total_regulares,
        total_irregulares=total_irregulares,
        percentual_regular=percentual_regular,
        percentual_irregular=percentual_irregular,
        protocolos=protocolos_lista,
        resultado_programa=resultado_programa,
        distribuicao_por_safra=distribuicao_safra,
        distribuicao_motivo_saida=distribuicao_motivos,
        tempo_medio_irregularidade=tempo_medio_lista,
        distribuicao_tempo_irregularidade=distribuicao_tempo,
        taxa_resolucao_mensal=taxa_resolucao,
        data_atualizacao=None,
    )


# ---------------------------------------------------------------------------
# Legacy Polars compute path (used by BigQueryDashboardRepository / V1)
# ---------------------------------------------------------------------------


def _calculate_dashboard_metrics(df: pl.DataFrame, filtro_secretaria: str | None = None) -> Dashboard:
    import time as perf_time

    # =========================================================================
    # SEÇÃO 4 + 5: SAFRAS E MOTIVOS (Polars nativo - instantâneo)
    # =========================================================================
    section_start = perf_time.perf_counter()

    df_with_qtd = df.with_columns([
        pl.col("indicador_participantes_qtd_total").cast(pl.Int64).fill_null(1).alias("qtd"),
        pl.col("pic_status").fill_null("").str.to_lowercase().alias("status_lower"),
        pl.col("pic_cohort").cast(pl.Utf8).str.slice(0, 7).alias("cohort_str"),
    ])

    safra_df = (
        df_with_qtd
        .filter(pl.col("cohort_str").is_not_null() & (pl.col("cohort_str") != ""))
        .group_by("cohort_str", "status_lower")
        .agg(pl.col("qtd").sum().alias("total"))
    )

    safras_agregadas: dict[str, dict[str, int]] = defaultdict(lambda: {"ativos": 0, "inativos": 0})
    for row in safra_df.iter_rows(named=True):
        cohort = row["cohort_str"]
        status = row["status_lower"]
        total = row["total"] or 0
        if status == "ativo":
            safras_agregadas[cohort]["ativos"] += total
        else:
            safras_agregadas[cohort]["inativos"] += total

    motivos_df = (
        df_with_qtd
        .filter(pl.col("status_lower") == "inativo")
        .with_columns([
            pl.col("pic_status_inativo_motivo").fill_null("Não informado").alias("motivo")
        ])
        .group_by("motivo")
        .agg(pl.col("qtd").sum().alias("total"))
    )

    motivos_saida: dict[str, int] = {}
    for row in motivos_df.iter_rows(named=True):
        motivo = row["motivo"] or "Não informado"
        motivos_saida[motivo.strip() if motivo.strip() else "Não informado"] = row["total"] or 0

    logger.info(f"⚡ Seções 4+5 (Safras+Motivos): {perf_time.perf_counter() - section_start:.3f}s")

    # =========================================================================
    # SEÇÃO 1: INDICADORES PRINCIPAIS (Polars struct.field - instantâneo)
    # =========================================================================
    section_start = perf_time.perf_counter()

    participantes_regular_num = df.select(
        pl.col("indicador_participantes_percentual_regular").struct.field("numerador").sum()
    ).item() or 0

    participantes_regular_den = df.select(
        pl.col("indicador_participantes_percentual_regular").struct.field("denominador").sum()
    ).item() or 0

    participantes_irregular_num = df.select(
        pl.col("indicador_participantes_percentual_irregular").struct.field("numerador").sum()
    ).item() or 0

    logger.info(f"⚡ Seção 1 (Indicadores): {perf_time.perf_counter() - section_start:.3f}s")

    # =========================================================================
    # SEÇÃO 2: PROTOCOLOS (explode + struct.field + group_by)
    # =========================================================================
    section_start = perf_time.perf_counter()

    protocolos_agregados: dict[str, dict[str, Any]] = {}

    if "indicador_protocolos_percentual_regular" in df.columns:
        df_protocolos = (
            df.select(pl.col("indicador_protocolos_percentual_regular"))
            .explode("indicador_protocolos_percentual_regular")
            .filter(pl.col("indicador_protocolos_percentual_regular").is_not_null())
        )

        if len(df_protocolos) > 0:
            df_protocolos = df_protocolos.with_columns([
                pl.col("indicador_protocolos_percentual_regular").struct.field("protocolo_id").alias("protocolo_id"),
                pl.col("indicador_protocolos_percentual_regular").struct.field("protocolo_descricao").alias("descricao"),
                pl.col("indicador_protocolos_percentual_regular").struct.field("protocolo_secretaria").alias("secretaria"),
                pl.col("indicador_protocolos_percentual_regular").struct.field("valor_mais_recente").alias("valor_recente"),
            ])

            df_protocolos = df_protocolos.with_columns([
                pl.col("valor_recente").list.first().alias("valor_recente_first"),
            ])

            df_protocolos = df_protocolos.with_columns([
                pl.col("valor_recente_first").struct.field("indicador_numerador").alias("num"),
                pl.col("valor_recente_first").struct.field("indicador_denominador").alias("den"),
            ])

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

    evolucao_mensal: dict[str, dict[str, dict[str, int]]] = defaultdict(
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
                pass

    logger.info(f"⚡ Seção 3 (Série Temporal): {perf_time.perf_counter() - section_start:.3f}s")

    # =========================================================================
    # SEÇÃO 6: TEMPO DE IRREGULARIDADE (explode + agregações)
    # =========================================================================
    section_start = perf_time.perf_counter()

    tempo_irregular_por_secretaria: dict[str, list[int]] = defaultdict(list)

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

            df_valores = (
                df_tempo
                .filter(pl.col("secretaria").is_not_null())
                .explode("valores")
                .filter(pl.col("valores").is_not_null() & (pl.col("valores") > 0))
            )

            if len(df_valores) > 0:
                for row in df_valores.select(["secretaria", "valores"]).iter_rows():
                    secretaria, valor = row
                    tempo_irregular_por_secretaria[secretaria].append(valor)
                    tempo_irregular_por_secretaria["geral"].append(valor)

    logger.info(f"⚡ Seção 6 (Tempo Irregularidade): {perf_time.perf_counter() - section_start:.3f}s")

    # =========================================================================
    # SEÇÃO 7: TAXA DE RESOLUÇÃO MENSAL (explode + group_by)
    # =========================================================================
    section_start = perf_time.perf_counter()

    resolucao_mensal: dict[str, dict[str, dict[str, int]]] = defaultdict(
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

    total_participantes = participantes_regular_den
    total_regulares = participantes_regular_num
    total_irregulares = participantes_irregular_num
    perc_regular = (total_regulares / total_participantes * 100) if total_participantes > 0 else 0.0
    perc_irregular = (total_irregulares / total_participantes * 100) if total_participantes > 0 else 0.0

    protocolos_lista: list[ProtocoloIndicador] = []
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

    resultado_programa: list[ResultadoProgramaPoint] = []
    for mes in sorted(evolucao_mensal.keys()):
        dados_mes = evolucao_mensal[mes]

        def calc_perc(sec: str, dados_mes: dict = dados_mes) -> float:
            d = dados_mes.get(sec, {"num": 0, "den": 0})
            return round(d["num"] / d["den"] * 100, 1) if d["den"] > 0 else 0.0
        resultado_programa.append(
            ResultadoProgramaPoint(
                mes=mes, mes_label=_format_mes_label(mes),
                todos=calc_perc("TODOS"), saude=calc_perc("SMS"),
                educacao=calc_perc("SME"), assistencia=calc_perc("SMAS"),
            )
        )

    distribuicao_safra: list[DistribuicaoSafra] = []
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

    distribuicao_motivos: list[DistribuicaoMotivoSaida] = [
        DistribuicaoMotivoSaida(motivo=m, total=t)
        for m, t in sorted(motivos_saida.items(), key=lambda x: x[1], reverse=True)
    ]

    mapa_labels = {"geral": "Geral", "smas": "Assistência Social", "sme": "Educação", "sms": "Saúde"}
    tempo_medio_lista: list[TempoMedioIrregularidade] = []

    if filtro_secretaria:
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

    todos_valores = tempo_irregular_por_secretaria.get("geral", [])
    total_valores = len(todos_valores)
    faixas_config = [("0-30", "0-30 dias", 0, 30), ("31-60", "31-60 dias", 31, 60),
                     ("61-90", "61-90 dias", 61, 90), ("90+", "90+ dias", 91, float("inf"))]
    distribuicao_tempo: list[DistribuicaoTempoIrregularidade] = []
    for faixa, faixa_label, min_d, max_d in faixas_config:
        count = sum(1 for v in todos_valores if min_d <= v <= max_d)
        distribuicao_tempo.append(
            DistribuicaoTempoIrregularidade(
                faixa=faixa, faixa_label=faixa_label, count=count,
                percentual=round(count / total_valores * 100, 1) if total_valores > 0 else 0.0,
            )
        )

    taxa_resolucao_lista: list[TaxaResolucaoMensalPoint] = []
    for mes in sorted(resolucao_mensal.keys()):
        dados_mes = resolucao_mensal[mes]

        def calc_res(sec: str, dados_mes: dict = dados_mes) -> float:
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
