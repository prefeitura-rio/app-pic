"""
compute_postgrest.py — Cálculo das métricas do dashboard com dados do PostgREST.

Dados já vêm agregados em SQL pelo PostgREST; Python apenas acumula quando
houver mais de uma linha por chave e constrói os objetos de domínio.
"""

from collections import defaultdict
from typing import Any

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
# Helpers
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


def _percentual_raw(num: int | float, den: int | float) -> float:
    """Raw percentage (sem rounding) — usado para calcular complemento."""
    if not den or den <= 0:
        return 0.0
    return num / den * 100


# ---------------------------------------------------------------------------
# PostgREST compute path (dados pré-agregados)
# ---------------------------------------------------------------------------


def _calculate_dashboard_metrics(
    consolidado: dict[str, Any],
    protocolos: list[dict[str, Any]],
    series: list[dict[str, Any]],
    tempo: dict[str, Any],
    resolucao: list[dict[str, Any]],
    filtro_secretaria: str | None = None,
) -> Dashboard:
    """Compute all seven dashboard sections from PostgREST data.

    Os dados já vêm agregados do banco; quando houver mais de uma linha por
    chave (ex.: protocolos repetidos entre dimensões), as linhas são somadas.

    Args:
        consolidado: Output of ``_fetch_consolidado``:
            {"totals": {regular_num, regular_den, irregular_num},
             "safras": [{cohort, status, qtd}],
             "motivos": [{motivo, qtd}]}
        protocolos: linhas por protocolo_id
        series: linhas por (mes, serie_tipo)
        tempo: {smas, sme, sms} com somas ponderadas pré-calculadas
        resolucao: linhas por (mes, secretaria)
        filtro_secretaria: Optional secretaria param (SMS|SME|SMAS)

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

    logger.info(f"⚡ [postgrest_v2] Seção 1: {perf_time.perf_counter() - t0:.3f}s")

    # =========================================================================
    # SECTION 2 — Protocolos (agrega linhas repetidas por protocolo_id)
    # =========================================================================
    t1 = perf_time.perf_counter()

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
        perc_reg_raw = _percentual_raw(num, den)
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

    logger.info(f"⚡ [postgrest_v2] Seção 2: {perf_time.perf_counter() - t1:.3f}s")

    # =========================================================================
    # SECTION 3 — Resultado do programa (dados já agregados)
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

    logger.info(f"⚡ [postgrest_v2] Seção 3: {perf_time.perf_counter() - t1:.3f}s")

    # =========================================================================
    # SECTION 4 — Distribuição por safra (dados já agregados)
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
        # QUIRK 3: qtd NULL → 1
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

    logger.info(f"⚡ [postgrest_v2] Seção 4: {perf_time.perf_counter() - t1:.3f}s")

    # =========================================================================
    # SECTION 5 — Distribuição por motivo de saída (dados já agregados)
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

    logger.info(f"⚡ [postgrest_v2] Seção 5: {perf_time.perf_counter() - t1:.3f}s")

    # =========================================================================
    # SECTION 6 — Tempo de irregularidade (faixas pré-agregadas no banco)
    # =========================================================================
    t1 = perf_time.perf_counter()

    # QUIRK 6: filtro_secretaria restricts which bands appear in tempo_medio
    if filtro_secretaria:
        secretarias_incluir = ["geral", filtro_secretaria.lower()]
    else:
        secretarias_incluir = ["geral", "smas", "sme", "sms"]

    # --- Tempo médio por secretaria (média já vem do banco via AVG()) ---------
    # QUIRK 5: "geral" total = soma dos totais das 3 secretarias
    def _total_sec(sec: str) -> int:
        d = tempo.get(sec, {})
        return (
            int(d.get("faixa_0_30") or 0)
            + int(d.get("faixa_31_60") or 0)
            + int(d.get("faixa_61_90") or 0)
            + int(d.get("faixa_91_mais") or 0)
        )

    total_por_sec = {sec: _total_sec(sec) for sec in ("smas", "sme", "sms")}
    total_geral_calc = sum(total_por_sec.values())

    tempo_medio_lista: list[TempoMedioIrregularidade] = []
    for sec in secretarias_incluir:
        if sec == "geral":
            # Média ponderada: soma(media_sec * total_sec) / total_geral
            soma_pond = sum(
                float(tempo.get(s, {}).get("media") or 0.0) * total_por_sec[s]
                for s in ("smas", "sme", "sms")
            )
            media = round(soma_pond / total_geral_calc, 1) if total_geral_calc > 0 else 0.0
            total = total_geral_calc
        else:
            media = round(float(tempo.get(sec, {}).get("media") or 0.0), 1)
            total = total_por_sec.get(sec, 0)
        tempo_medio_lista.append(
            TempoMedioIrregularidade(
                secretaria=sec,
                secretaria_label=_MAPA_SECRETARIA_LABEL.get(sec, sec.upper()),
                tempo_medio_dias=media,
                total_irregulares=total,
            )
        )

    # --- Histograma de faixas (SUM vindo direto do banco) --------------------
    # Usa as colunas geral_irregularidade_faixa_* que já agregam smas+sme+sms
    geral = tempo.get("geral", {})
    faixa_counts: dict[str, int] = {
        "0-30":  int(geral.get("faixa_0_30") or 0),
        "31-60": int(geral.get("faixa_31_60") or 0),
        "61-90": int(geral.get("faixa_61_90") or 0),
        "90+":   int(geral.get("faixa_91_mais") or 0),
    }
    total_geral = sum(faixa_counts.values())

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

    logger.info(f"⚡ [postgrest_v2] Seção 6: {perf_time.perf_counter() - t1:.3f}s")

    # =========================================================================
    # SECTION 7 — Taxa de resolução mensal (dados pré-agregados)
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
        # Dados já agregados — acumular caso haja linhas repetidas
        resolucao_agg[mes][nome_sec]["num"] += num
        resolucao_agg[mes][nome_sec]["den"] += den
        # QUIRK 7: TODOS accumulates every secretaria
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

    logger.info(f"⚡ [postgrest_v2] Seção 7: {perf_time.perf_counter() - t1:.3f}s")
    logger.info(f"⚡ [postgrest_v2] total compute: {perf_time.perf_counter() - t0:.3f}s")

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
