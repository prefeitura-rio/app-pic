"""Unit tests for PostgrestDashboardRepository and compute functions.

Uses the same FakeDataProxy pattern from test_postgrest_participant_repository
to mock the data-proxy without any real network or Redis.

Coverage:
    - _calculate_dashboard_metrics_postgrest (all 7 sections + 7 quirks)
    - PostgrestDashboardRepository._fetch_* (filters forwarded to PostgREST)
    - Cache hit / cache miss / bypass_cache
    - Empty result set → all-zeros Dashboard
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.pic.domain.models.dashboard import Dashboard
from src.pic.infrastructure.dashboard.compute import (
    _calculate_dashboard_metrics_postgrest,
)
from src.pic.infrastructure.dashboard.compute_postgrest import (
    _calculate_dashboard_metrics_postgrest_v2,
)
from src.pic.infrastructure.postgrest_client.client import PostgrestClient
from src.pic.infrastructure.postgrest_client.config import PostgrestClientConfig
from src.pic.infrastructure.repositories.postgrest_dashboard_repository import (
    _TABLE_CONSOLIDADO,
    _TABLE_PROTOCOLOS,
    _TABLE_RESOLUCAO,
    _TABLE_SERIES,
    _TABLE_TEMPO,
    PostgrestDashboardRepository,
    _make_cache_key,
)

# ---------------------------------------------------------------------------
# Shared test config & helpers
# ---------------------------------------------------------------------------

CONFIG = PostgrestClientConfig(
    base_url="https://data-proxy.example/",
    schema="app_pequenos_cariocas",
    token_url="https://keycloak.example/token",
    client_id="pic-client",
    client_secret="pic-secret",
)


class FakeDataProxy:
    """Minimal fake of the data-proxy PostgREST.

    Returns pre-canned rows keyed by table name. For consolidado,
    selects the correct sub-dataset based on select parameter.
    
    Keycloak token requests are answered with a dummy credential response 
    so the auth flow does not block.
    """

    def __init__(self, rows_by_table: dict[str, list[dict]]) -> None:
        self.rows_by_table = rows_by_table
        self.requests: list[httpx.Request] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "keycloak.example":
            return httpx.Response(
                200,
                json={"access_token": "test-token", "expires_in": 3600},
            )
        self.requests.append(request)
        
        # Extract table name from path
        path = request.url.path.lstrip("/")
        table = path.split(".")[-1]  # Handle schema.table format
        
        # Special handling for consolidado (has 3 different responses)
        if table == _TABLE_CONSOLIDADO:
            # Only return default data if consolidado is in rows_by_table
            if _TABLE_CONSOLIDADO not in self.rows_by_table:
                rows = []
            else:
                select_param = request.url.params.get("select", "")
                if ".sum()" in select_param:
                    # Totals request
                    rows = CONSOLIDADO_TOTALS
                elif "pic_cohort" in select_param:
                    # Safras request
                    rows = CONSOLIDADO_SAFRAS
                elif "pic_status_inativo_motivo" in select_param:
                    # Motivos request
                    rows = CONSOLIDADO_MOTIVOS
                else:
                    rows = []
        else:
            # Other tables
            rows = self.rows_by_table.get(table, [])
        
        return httpx.Response(200, json=rows, request=request)


def _make_repo(
    rows_by_table: dict[str, list[dict]],
    redis_client=None,
) -> tuple[PostgrestDashboardRepository, FakeDataProxy]:
    fake = FakeDataProxy(rows_by_table)
    client = PostgrestClient(CONFIG, transport=httpx.MockTransport(fake))
    return PostgrestDashboardRepository(client, redis_client=redis_client), fake


# ---------------------------------------------------------------------------
# Sample data fixtures
# ---------------------------------------------------------------------------

# Mock de dados AGREGADOS (como viria do PostgREST com .sum())
CONSOLIDADO_TOTALS = [
    {
        "regular_num": 10,       # sum(regular_numerador) = 3+7
        "regular_den": 14,       # sum(regular_denominador) = 4+10
        "irregular_num": 2,      # sum(irregular_numerador) = 1+1
    }
]

CONSOLIDADO_SAFRAS = [
    {
        "pic_cohort": "2025-01-10",
        "pic_status": "Ativo",
        "qtd": 1,  # sum(participante_quantidade) — NULL → 1
    },
    {
        "pic_cohort": "2025-01-15",
        "pic_status": "Inativo",
        "qtd": 2,
    },
]

CONSOLIDADO_MOTIVOS = [
    {
        "pic_status_inativo_motivo": None,
        "qtd": 2,  # Agregado
    },
]

# Mock de dados AGREGADOS por protocolo_id
PROTOCOLOS_ROWS = [
    {
        "protocolo_id": "p_sms",
        "protocolo_descricao": "Vacinação",
        "protocolo_secretaria": "SMS",
        "numerador": 8,   # sum(protocolo_regular_numerador) = 6+2
        "denominador": 15,  # sum(protocolo_regular_denominador) = 10+5
    },
]

# Mock de dados AGREGADOS por data e tipo
SERIES_ROWS = [
    # alias:coluna.sum() → PostgREST retorna a chave como o alias definido
    {"serie_tipo": "geral", "data_referencia_mensal": "2025-01-01", "numerador": 10, "denominador": 14},
    {"serie_tipo": "sms",  "data_referencia_mensal": "2025-01-01", "numerador": 5,  "denominador": 7},
    {"serie_tipo": "sme",  "data_referencia_mensal": "2025-01-01", "numerador": 3,  "denominador": 5},
    {"serie_tipo": "smas", "data_referencia_mensal": "2025-01-01", "numerador": 2,  "denominador": 2},
]

# Mock de dados AGREGADOS (faixas pré-calculadas no banco, PostgREST aplica SUM/AVG)
# PostgREST retorna 1 linha com aliases definidos no select
TEMPO_ROWS = [
    {
        # SMAS: média 15 dias, 2 pessoas na faixa 0-30
        "smas_media":          15.0,
        "smas_faixa_0_30":     2,
        "smas_faixa_31_60":    0,
        "smas_faixa_61_90":    0,
        "smas_faixa_91_mais":  0,
        # SME: média 45 dias, 0 pessoas (sem irregulares)
        "sme_media":           45.0,
        "sme_faixa_0_30":      0,
        "sme_faixa_31_60":     0,
        "sme_faixa_61_90":     0,
        "sme_faixa_91_mais":   0,
        # SMS: média 20 dias, 1 pessoa na faixa 0-30
        "sms_media":           20.0,
        "sms_faixa_0_30":      1,
        "sms_faixa_31_60":     0,
        "sms_faixa_61_90":     0,
        "sms_faixa_91_mais":   0,
        # GERAL: pré-agregado no banco (smas+sme+sms)
        "geral_faixa_0_30":    3,  # 2+0+1
        "geral_faixa_31_60":   0,
        "geral_faixa_61_90":   0,
        "geral_faixa_91_mais": 0,
    },
]

# Mock de dados AGREGADOS por secretaria e data
RESOLUCAO_ROWS = [
    {"secretaria": "sms", "data_referencia_mensal": "2025-01-01", "numerador": 8, "denominador": 10},
    {"secretaria": "smas", "data_referencia_mensal": "2025-01-01", "numerador": 3, "denominador": 5},
]

# Mock de dados AGREGADOS (como viria do PostgREST)
# FakeDataProxy será inteligente e retornará dados agregados por tabela
ALL_TABLES: dict[str, list[dict]] = {
    _TABLE_CONSOLIDADO: CONSOLIDADO_TOTALS,  # Placeholder — será resolvido por tabla name
    _TABLE_PROTOCOLOS: PROTOCOLOS_ROWS,
    _TABLE_SERIES: SERIES_ROWS,
    _TABLE_TEMPO: TEMPO_ROWS,
    _TABLE_RESOLUCAO: RESOLUCAO_ROWS,
}

# ---------------------------------------------------------------------------
# Tests: _calculate_dashboard_metrics_postgrest
# ---------------------------------------------------------------------------


class TestSection1Indicadores:
    """Section 1 — totals and percentages."""

    def _compute(self, **kwargs) -> Dashboard:
        defaults: dict = dict(
            consolidado={"totals": {}, "safras": [], "motivos": []},
            protocolos=[],
            series=[],
            tempo={},
            resolucao=[],
        )
        defaults.update(kwargs)
        return _calculate_dashboard_metrics_postgrest(**defaults)

    def test_basic_totals(self):
        result = self._compute(
            consolidado={
                "totals": {"regular_num": 10, "regular_den": 20, "irregular_num": 5},
                "safras": [],
                "motivos": [],
            }
        )
        assert result.total_participantes == 20  # QUIRK 1: uses regular_den
        assert result.total_regulares == 10
        assert result.total_irregulares == 5
        assert result.percentual_regular == 50.0
        assert result.percentual_irregular == 25.0

    def test_zero_denominador_yields_zero_percentual(self):
        result = self._compute(
            consolidado={
                "totals": {"regular_num": 0, "regular_den": 0, "irregular_num": 0},
                "safras": [],
                "motivos": [],
            }
        )
        assert result.total_participantes == 0
        assert result.percentual_regular == 0.0
        assert result.percentual_irregular == 0.0

    def test_null_values_treated_as_zero(self):
        result = self._compute(
            consolidado={
                "totals": {"regular_num": None, "regular_den": None, "irregular_num": None},
                "safras": [],
                "motivos": [],
            }
        )
        assert result.total_participantes == 0
        assert result.total_regulares == 0
        assert result.total_irregulares == 0


class TestSection2Protocolos:
    """Section 2 — protocols with QUIRK 2 (unrounded complement)."""

    def _compute(self, protocolos: list[dict]) -> Dashboard:
        return _calculate_dashboard_metrics_postgrest(
            consolidado={"totals": {}, "safras": [], "motivos": []},
            protocolos=protocolos,
            series=[],
            tempo={},
            resolucao=[],
        )

    def test_quirk_complement_unrounded(self):
        """percentual_irregular = round(100 - perc_raw, 1), not 100 - round(...)."""
        # 53/100 = 53.0 → complement = 47.0 (trivial)
        result = self._compute([{
            "protocolo_id": "p1",
            "protocolo_descricao": "Proto A",
            "protocolo_secretaria": "SMS",
            "numerador": 53,
            "denominador": 100,
        }])
        p = result.protocolos[0]
        assert p.percentual_regular == 53.0
        assert p.percentual_irregular == 47.0

    def test_quirk_complement_precision(self):
        """6/11 = 54.545…% → regular 54.5, irregular 45.5 (not 100 - 54.5 = 45.5 same here,
        but the point is we use the raw value before rounding)."""
        result = self._compute([{
            "protocolo_id": "p2",
            "protocolo_descricao": "Proto B",
            "protocolo_secretaria": "SME",
            "numerador": 6,
            "denominador": 11,
        }])
        p = result.protocolos[0]
        raw = 6 / 11 * 100  # 54.545...
        assert p.percentual_regular == round(raw, 1)
        assert p.percentual_irregular == round(100 - raw, 1)

    def test_aggregates_same_protocolo_id(self):
        """Rows with the same protocolo_id must be summed.

        Note: _calculate_dashboard_metrics_postgrest expects the already-mapped
        field names (numerador/denominador), not the raw PostgREST column names
        (protocolo_regular_numerador/protocolo_regular_denominador).  Those are
        mapped by _fetch_protocolos before reaching the compute layer.
        """
        rows = [
            {"protocolo_id": "p_sms", "protocolo_descricao": "Vacinação", "protocolo_secretaria": "SMS", "numerador": 6, "denominador": 10},
            {"protocolo_id": "p_sms", "protocolo_descricao": "Vacinação", "protocolo_secretaria": "SMS", "numerador": 2, "denominador": 5},
        ]
        result = self._compute(rows)
        assert len(result.protocolos) == 1
        p = result.protocolos[0]
        assert p.numerador == 8    # 6 + 2
        assert p.denominador == 15  # 10 + 5

    def test_sorted_by_secretaria_then_descricao(self):
        protocolos = [
            {"protocolo_id": "b", "protocolo_descricao": "Z Proto", "protocolo_secretaria": "SMS", "numerador": 1, "denominador": 2},
            {"protocolo_id": "a", "protocolo_descricao": "A Proto", "protocolo_secretaria": "SMAS", "numerador": 1, "denominador": 2},
            {"protocolo_id": "c", "protocolo_descricao": "M Proto", "protocolo_secretaria": "SMS", "numerador": 1, "denominador": 2},
        ]
        result = self._compute(protocolos)
        ids = [p.protocolo_id for p in result.protocolos]
        assert ids == ["a", "c", "b"]  # SMAS first, then SMS A-Z

    def test_zero_denominador_gives_zero_percentuals(self):
        result = self._compute([{
            "protocolo_id": "p3",
            "protocolo_descricao": "Proto C",
            "protocolo_secretaria": "SMS",
            "numerador": 5,
            "denominador": 0,
        }])
        p = result.protocolos[0]
        assert p.percentual_regular == 0.0
        assert p.percentual_irregular == 0.0

    def test_null_protocolo_id_ignored(self):
        result = self._compute([{
            "protocolo_id": None,
            "protocolo_descricao": "Should be ignored",
            "protocolo_secretaria": "SMS",
            "numerador": 5,
            "denominador": 10,
        }])
        assert result.protocolos == []


class TestSection3Serie:
    """Section 3 — monthly result programme."""

    def _compute(self, series: list[dict]) -> Dashboard:
        return _calculate_dashboard_metrics_postgrest(
            consolidado={"totals": {}, "safras": [], "motivos": []},
            protocolos=[],
            series=series,
            tempo={},
            resolucao=[],
        )

    def test_maps_geral_to_todos(self):
        result = self._compute([
            {"serie_tipo": "geral", "mes": "2025-01", "numerador": 10, "denominador": 20},
        ])
        assert len(result.resultado_programa) == 1
        assert result.resultado_programa[0].todos == 50.0

    def test_maps_sms_sme_smas(self):
        result = self._compute([
            {"serie_tipo": "sms",  "mes": "2025-01", "numerador": 5, "denominador": 10},
            {"serie_tipo": "sme",  "mes": "2025-01", "numerador": 3, "denominador": 6},
            {"serie_tipo": "smas", "mes": "2025-01", "numerador": 2, "denominador": 4},
        ])
        r = result.resultado_programa[0]
        assert r.saude == 50.0
        assert r.educacao == 50.0
        assert r.assistencia == 50.0

    def test_sorted_by_mes_asc(self):
        result = self._compute([
            {"serie_tipo": "geral", "mes": "2025-03", "numerador": 1, "denominador": 1},
            {"serie_tipo": "geral", "mes": "2025-01", "numerador": 1, "denominador": 1},
            {"serie_tipo": "geral", "mes": "2025-02", "numerador": 1, "denominador": 1},
        ])
        meses = [r.mes for r in result.resultado_programa]
        assert meses == ["2025-01", "2025-02", "2025-03"]

    def test_mes_label_formatted(self):
        result = self._compute([
            {"serie_tipo": "geral", "mes": "2025-07", "numerador": 1, "denominador": 1},
        ])
        assert result.resultado_programa[0].mes_label == "Jul/25"


class TestSection4Safras:
    """Section 4 — distribution by cohort (safra)."""

    def _compute(self, safras: list[dict]) -> Dashboard:
        return _calculate_dashboard_metrics_postgrest(
            consolidado={"totals": {}, "safras": safras, "motivos": []},
            protocolos=[],
            series=[],
            tempo={},
            resolucao=[],
        )

    def test_ativo_vs_inativo(self):
        result = self._compute([
            {"cohort": "2025-01-10", "status": "Ativo", "qtd": 5},
            {"cohort": "2025-01-20", "status": "Inativo", "qtd": 3},
        ])
        assert len(result.distribuicao_por_safra) == 1
        s = result.distribuicao_por_safra[0]
        assert s.total_ativos == 5
        assert s.total_inativos == 3
        assert s.total_participantes == 8

    def test_quirk_null_qtd_fallback_to_1(self):
        """QUIRK 3: NULL qtd → 1."""
        result = self._compute([
            {"cohort": "2025-01-01", "status": "Ativo", "qtd": None},
        ])
        assert result.distribuicao_por_safra[0].total_ativos == 1

    def test_quirk_non_ativo_counts_as_inativo(self):
        """Any status other than 'ativo' counts as inactive (case-insensitive)."""
        result = self._compute([
            {"cohort": "2025-01-01", "status": None, "qtd": 1},
            {"cohort": "2025-01-01", "status": "desligado", "qtd": 2},
            {"cohort": "2025-01-01", "status": "ATIVO", "qtd": 3},
        ])
        s = result.distribuicao_por_safra[0]
        assert s.total_ativos == 3
        assert s.total_inativos == 3

    def test_cohort_sliced_to_yyyy_mm(self):
        """Full date strings should be sliced to YYYY-MM before grouping."""
        result = self._compute([
            {"cohort": "2025-01-10", "status": "Ativo", "qtd": 1},
            {"cohort": "2025-01-20", "status": "Ativo", "qtd": 2},
        ])
        # Both belong to the same safra
        assert len(result.distribuicao_por_safra) == 1
        assert result.distribuicao_por_safra[0].total_ativos == 3

    def test_safra_label_formatted(self):
        result = self._compute([{"cohort": "2025-07-01", "status": "Ativo", "qtd": 1}])
        assert result.distribuicao_por_safra[0].safra == "Jul/25"

    def test_sorted_asc(self):
        result = self._compute([
            {"cohort": "2025-03-01", "status": "Ativo", "qtd": 1},
            {"cohort": "2025-01-01", "status": "Ativo", "qtd": 1},
        ])
        safras = [s.safra for s in result.distribuicao_por_safra]
        assert safras == ["Jan/25", "Mar/25"]

    def test_null_cohort_ignored(self):
        result = self._compute([{"cohort": None, "status": "Ativo", "qtd": 5}])
        assert result.distribuicao_por_safra == []


class TestSection5Motivos:
    """Section 5 — distribution by exit reason (only inativo rows)."""

    def _compute(self, motivos: list[dict]) -> Dashboard:
        return _calculate_dashboard_metrics_postgrest(
            consolidado={"totals": {}, "safras": [], "motivos": motivos},
            protocolos=[],
            series=[],
            tempo={},
            resolucao=[],
        )

    def test_quirk_null_motivo_to_nao_informado(self):
        """QUIRK 4: NULL → 'Não informado'."""
        result = self._compute([{"motivo": None, "qtd": 5}])
        assert result.distribuicao_motivo_saida[0].motivo == "Não informado"
        assert result.distribuicao_motivo_saida[0].total == 5

    def test_quirk_blank_motivo_to_nao_informado(self):
        """QUIRK 4: whitespace-only string → 'Não informado'."""
        result = self._compute([{"motivo": "   ", "qtd": 3}])
        assert result.distribuicao_motivo_saida[0].motivo == "Não informado"

    def test_motivo_stripped(self):
        result = self._compute([{"motivo": "  saída do programa  ", "qtd": 10}])
        assert result.distribuicao_motivo_saida[0].motivo == "saída do programa"

    def test_sorted_by_total_desc(self):
        result = self._compute([
            {"motivo": "A", "qtd": 2},
            {"motivo": "B", "qtd": 10},
            {"motivo": "C", "qtd": 5},
        ])
        totais = [m.total for m in result.distribuicao_motivo_saida]
        assert totais == sorted(totais, reverse=True)

    def test_null_and_blank_merge_into_nao_informado(self):
        result = self._compute([
            {"motivo": None, "qtd": 5},
            {"motivo": "", "qtd": 3},
        ])
        assert len(result.distribuicao_motivo_saida) == 1
        assert result.distribuicao_motivo_saida[0].total == 8

    def test_quirk_null_qtd_fallback_to_1(self):
        result = self._compute([{"motivo": None, "qtd": None}])
        assert result.distribuicao_motivo_saida[0].total == 1


class TestSection6Tempo:
    """Section 6 — irregular time average and histogram.

    Nova estrutura: faixas pré-agregadas no banco (faixa_0_30/31_60/61_90/91_mais)
    e médias via AVG() do PostgREST. Python apenas soma e monta objetos.

    Usa _calculate_dashboard_metrics_postgrest_v2 (compute_postgrest.py).
    """

    def _compute(self, tempo: dict, filtro_secretaria=None) -> Dashboard:
        return _calculate_dashboard_metrics_postgrest_v2(
            consolidado={"totals": {}, "safras": [], "motivos": []},
            protocolos=[],
            series=[],
            tempo=tempo,
            resolucao=[],
            filtro_secretaria=filtro_secretaria,
        )

    def _tempo(
        self,
        smas_media=0.0, smas_0_30=0, smas_31_60=0, smas_61_90=0, smas_91=0,
        sme_media=0.0,  sme_0_30=0,  sme_31_60=0,  sme_61_90=0,  sme_91=0,
        sms_media=0.0,  sms_0_30=0,  sms_31_60=0,  sms_61_90=0,  sms_91=0,
    ) -> dict:
        """Monta estrutura de tempo na nova forma esperada por compute_postgrest."""
        return {
            "smas": {"media": smas_media, "faixa_0_30": smas_0_30, "faixa_31_60": smas_31_60, "faixa_61_90": smas_61_90, "faixa_91_mais": smas_91},
            "sme":  {"media": sme_media,  "faixa_0_30": sme_0_30,  "faixa_31_60": sme_31_60,  "faixa_61_90": sme_61_90,  "faixa_91_mais": sme_91},
            "sms":  {"media": sms_media,  "faixa_0_30": sms_0_30,  "faixa_31_60": sms_31_60,  "faixa_61_90": sms_61_90,  "faixa_91_mais": sms_91},
            "geral": {
                "faixa_0_30":    smas_0_30  + sme_0_30  + sms_0_30,
                "faixa_31_60":   smas_31_60 + sme_31_60 + sms_31_60,
                "faixa_61_90":   smas_61_90 + sme_61_90 + sms_61_90,
                "faixa_91_mais": smas_91    + sme_91    + sms_91,
            },
        }

    def test_media_calculada_corretamente(self):
        """Média de smas=30 dias (10 pessoas), sem sme/sms → geral=30 dias, 10 pessoas."""
        tempo = self._tempo(smas_media=30.0, smas_0_30=10)
        result = self._compute(tempo)
        geral = next(t for t in result.tempo_medio_irregularidade if t.secretaria == "geral")
        smas  = next(t for t in result.tempo_medio_irregularidade if t.secretaria == "smas")
        assert smas.tempo_medio_dias == 30.0
        assert geral.tempo_medio_dias == 30.0
        assert geral.total_irregulares == 10

    def test_quirk_geral_soma_todas_secretarias(self):
        """QUIRK 5: 'geral' total_irregulares = soma das 3 secretarias."""
        # smas: 2 pessoas (1 na 0-30, 1 na 31-60)
        # sme:  4 pessoas (todas na 31-60)
        # sms:  6 pessoas (todas na 61-90)
        tempo = self._tempo(
            smas_media=50.0, smas_0_30=1, smas_31_60=1,
            sme_media=100.0,  sme_31_60=4,
            sms_media=150.0,  sms_61_90=6,
        )
        result = self._compute(tempo)
        geral = next(t for t in result.tempo_medio_irregularidade if t.secretaria == "geral")
        assert geral.total_irregulares == 12  # 2 + 4 + 6
        # Média ponderada: (50*2 + 100*4 + 150*6) / 12 = 1400/12 ≈ 116.7
        expected_media = round((50.0 * 2 + 100.0 * 4 + 150.0 * 6) / 12, 1)
        assert geral.tempo_medio_dias == expected_media

    def test_quirk_filtro_secretaria_restringe_bands(self):
        """QUIRK 6: filtro_secretaria limits bands to [geral, <secretaria>]."""
        tempo = self._tempo(
            smas_media=30.0, smas_0_30=2,
            sme_media=45.0,  sme_31_60=4,
            sms_media=70.0,  sms_61_90=6,
        )
        result = self._compute(tempo, filtro_secretaria="SMS")
        secs = {t.secretaria for t in result.tempo_medio_irregularidade}
        assert secs == {"geral", "sms"}

    def test_histograma_faixas_pre_agregadas(self):
        """Histograma usa colunas geral_faixa_* pré-agregadas do banco."""
        tempo = self._tempo(
            smas_media=15.0, smas_0_30=10,   # 10 pessoas em 0-30
            sme_media=45.0,  sme_31_60=5,    # 5 pessoas em 31-60
            sms_media=70.0,  sms_61_90=3,    # 3 pessoas em 61-90
        )
        result = self._compute(tempo)
        hist = {d.faixa: d.count for d in result.distribuicao_tempo_irregularidade}
        assert hist["0-30"]  == 10
        assert hist["31-60"] == 5
        assert hist["61-90"] == 3
        assert hist["90+"]   == 0

    def test_histograma_percentual(self):
        """Percentual = count / total_geral * 100."""
        tempo = self._tempo(smas_0_30=1, sme_31_60=3)  # total=4
        result = self._compute(tempo)
        hist = {d.faixa: d.percentual for d in result.distribuicao_tempo_irregularidade}
        assert hist["0-30"]  == round(1 / 4 * 100, 1)   # 25.0
        assert hist["31-60"] == round(3 / 4 * 100, 1)   # 75.0
        assert hist["61-90"] == 0.0
        assert hist["90+"]   == 0.0

    def test_histograma_ordenacao_fixa(self):
        result = self._compute({})
        faixas = [d.faixa for d in result.distribuicao_tempo_irregularidade]
        assert faixas == ["0-30", "31-60", "61-90", "90+"]

    def test_empty_tempo_returns_zeros(self):
        result = self._compute({})
        geral = next(t for t in result.tempo_medio_irregularidade if t.secretaria == "geral")
        assert geral.tempo_medio_dias == 0.0
        assert geral.total_irregulares == 0


class TestSection7Resolucao:
    """Section 7 — monthly resolution rate."""

    def _compute(self, resolucao: list[dict]) -> Dashboard:
        return _calculate_dashboard_metrics_postgrest(
            consolidado={"totals": {}, "safras": [], "motivos": []},
            protocolos=[],
            series=[],
            tempo={},
            resolucao=resolucao,
        )

    def test_quirk_todos_acumula_todas_secretarias(self):
        """QUIRK 7: TODOS = sum of all secretarias including 'GERAL'."""
        result = self._compute([
            {"secretaria": "sms",  "mes": "2025-01", "numerador": 8, "denominador": 10},
            {"secretaria": "smas", "mes": "2025-01", "numerador": 3, "denominador": 5},
        ])
        r = result.taxa_resolucao_mensal[0]
        # TODOS: num=11, den=15
        assert r.todos == round(11 / 15 * 100, 1)
        assert r.saude == round(8 / 10 * 100, 1)
        assert r.assistencia == round(3 / 5 * 100, 1)

    def test_sorted_by_mes_asc(self):
        result = self._compute([
            {"secretaria": "sms", "mes": "2025-03", "numerador": 1, "denominador": 1},
            {"secretaria": "sms", "mes": "2025-01", "numerador": 1, "denominador": 1},
        ])
        meses = [r.mes for r in result.taxa_resolucao_mensal]
        assert meses == ["2025-01", "2025-03"]

    def test_unknown_secretaria_becomes_upper(self):
        result = self._compute([
            {"secretaria": "geral", "mes": "2025-01", "numerador": 5, "denominador": 10},
        ])
        # "geral" → "GERAL" and should be accumulated in TODOS too
        r = result.taxa_resolucao_mensal[0]
        assert r.todos == 50.0  # accumulated from "GERAL"

    def test_mes_label_formatted(self):
        result = self._compute([
            {"secretaria": "sms", "mes": "2025-12", "numerador": 1, "denominador": 1},
        ])
        assert result.taxa_resolucao_mensal[0].mes_label == "Dez/25"


class TestEmptyDashboard:
    """All-empty inputs must yield a fully zeroed Dashboard."""

    def test_all_zeros(self):
        result = _calculate_dashboard_metrics_postgrest(
            consolidado={"totals": {}, "safras": [], "motivos": []},
            protocolos=[],
            series=[],
            tempo={},
            resolucao=[],
        )
        assert result.total_participantes == 0
        assert result.total_regulares == 0
        assert result.total_irregulares == 0
        assert result.percentual_regular == 0.0
        assert result.percentual_irregular == 0.0
        assert result.protocolos == []
        assert result.resultado_programa == []
        assert result.distribuicao_por_safra == []
        assert result.distribuicao_motivo_saida == []
        assert result.data_atualizacao is None
        # histogram still returns 4 fixed faixas
        assert len(result.distribuicao_tempo_irregularidade) == 4


# ---------------------------------------------------------------------------
# Tests: PostgrestDashboardRepository (fetch layer)
# ---------------------------------------------------------------------------


class TestRepositoryFetches:
    """Verify that the repository forwards filters to PostgREST correctly
    and constructs the right Dashboard via the compute layer."""

    @pytest.mark.asyncio
    async def test_full_pipeline_no_filters(self):
        repo, _ = _make_repo(ALL_TABLES)
        result = await repo.get_dashboard_metrics(filters={})
        assert isinstance(result, Dashboard)
        # Section 1: 3+7=10 regulares, den=4+10=14
        assert result.total_participantes == 14
        assert result.total_regulares == 10
        assert result.total_irregulares == 2

    @pytest.mark.asyncio
    async def test_ilike_filter_sent_to_postgrest(self):
        repo, fake = _make_repo(ALL_TABLES)
        await repo.get_dashboard_metrics(filters={"pic_grupo": "Criança"})
        # All 5 tables should have received the filter
        params_list = [r.url.params for r in fake.requests]
        assert any("pic_grupo" in str(p) for p in params_list)

    @pytest.mark.asyncio
    async def test_exact_filter_for_id_columns(self):
        repo, fake = _make_repo(ALL_TABLES)
        await repo.get_dashboard_metrics(filters={"id_cras": "001"})
        params_list = [r.url.params for r in fake.requests]
        # Should use `eq.001` not `ilike.001`
        assert any("eq.001" in str(p) for p in params_list)

    @pytest.mark.asyncio
    async def test_bool_filter_for_has_bolsa_familia(self):
        repo, fake = _make_repo(ALL_TABLES)
        await repo.get_dashboard_metrics(filters={"has_bolsa_familia": True})
        params_list = [r.url.params for r in fake.requests]
        assert any("is.true" in str(p) for p in params_list)

    @pytest.mark.asyncio
    async def test_seven_requests_sent(self):
        """3 consolidado subfetches + 4 other tables = 7 requests."""
        repo, fake = _make_repo(ALL_TABLES)
        await repo.get_dashboard_metrics(filters={})
        assert len(fake.requests) == 7

    @pytest.mark.asyncio
    async def test_empty_tables_returns_zero_dashboard(self):
        repo, _ = _make_repo({})
        result = await repo.get_dashboard_metrics(filters={})
        assert result.total_participantes == 0
        assert result.protocolos == []

    @pytest.mark.asyncio
    async def test_filtro_secretaria_passed_to_compute(self):
        repo, _ = _make_repo(ALL_TABLES)
        result = await repo.get_dashboard_metrics(
            filters={}, secretaria="SMS"
        )
        secs = {t.secretaria for t in result.tempo_medio_irregularidade}
        assert secs == {"geral", "sms"}


class TestRepositoryCache:
    """Verify Redis cache read/write/bypass behaviour."""

    def _make_redis(self, cached_payload: dict | None = None):
        redis = MagicMock()
        if cached_payload is None:
            redis.get = AsyncMock(return_value=None)
        else:
            redis.get = AsyncMock(
                return_value=json.dumps(cached_payload).encode()
            )
        redis.set = AsyncMock()
        return redis

    @pytest.mark.asyncio
    async def test_cache_miss_writes_to_redis(self):
        redis = self._make_redis(None)
        repo, _ = _make_repo(ALL_TABLES, redis_client=redis)
        await repo.get_dashboard_metrics(filters={})
        redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cache_hit_skips_fetches(self):
        empty = Dashboard().model_dump()
        redis = self._make_redis(empty)
        repo, fake = _make_repo(ALL_TABLES, redis_client=redis)
        result = await repo.get_dashboard_metrics(filters={})
        # No PostgREST requests when cache hit
        assert len(fake.requests) == 0
        assert isinstance(result, Dashboard)

    @pytest.mark.asyncio
    async def test_bypass_cache_still_fetches(self):
        empty = Dashboard().model_dump()
        redis = self._make_redis(empty)
        repo, fake = _make_repo(ALL_TABLES, redis_client=redis)
        await repo.get_dashboard_metrics(filters={}, bypass_cache=True)
        # bypass_cache=True must skip cache read and go to PostgREST
        # 3 consolidado subfetches + 4 other tables = 7 requests
        assert len(fake.requests) == 7

    @pytest.mark.asyncio
    async def test_bypass_cache_still_writes_cache(self):
        redis = self._make_redis(None)
        repo, _ = _make_repo(ALL_TABLES, redis_client=redis)
        await repo.get_dashboard_metrics(filters={}, bypass_cache=True)
        redis.set.assert_awaited_once()


class TestCacheKey:
    """Verify the cache key is deterministic and isolated per user."""

    def test_key_deterministic_for_same_inputs(self):
        key1 = _make_cache_key({"bairro": "Copacabana"}, "SMS", "111.111.111-11")
        key2 = _make_cache_key({"bairro": "Copacabana"}, "SMS", "111.111.111-11")
        assert key1 == key2

    def test_key_isolates_by_user_id(self):
        key_a = _make_cache_key({"bairro": "Copacabana"}, "SMS", "111.111.111-11")
        key_b = _make_cache_key({"bairro": "Copacabana"}, "SMS", "222.222.222-22")
        assert key_a != key_b

    def test_key_isolates_by_filters(self):
        key_a = _make_cache_key({"bairro": "Copacabana"}, "SMS", "111.111.111-11")
        key_b = _make_cache_key({"bairro": "Leblon"}, "SMS", "111.111.111-11")
        assert key_a != key_b

    def test_key_isolates_by_secretaria(self):
        key_a = _make_cache_key({"bairro": "Copacabana"}, "SMS", "111.111.111-11")
        key_b = _make_cache_key({"bairro": "Copacabana"}, "SME", "111.111.111-11")
        assert key_a != key_b

    def test_key_isolates_none_user_id_from_empty_user_id(self):
        key_a = _make_cache_key({}, None, None)
        key_b = _make_cache_key({}, None, "")
        assert key_a != key_b

    @pytest.mark.asyncio
    async def test_repo_uses_user_id_in_cache_key(self):
        redis = MagicMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock()
        repo, _ = _make_repo(ALL_TABLES, redis_client=redis)
        await repo.get_dashboard_metrics(
            filters={"bairro": "Copacabana"},
            user_id="111.111.111-11",
        )
        expected = _make_cache_key({"bairro": "Copacabana"}, None, "111.111.111-11")
        redis.get.assert_awaited_once_with(expected)
