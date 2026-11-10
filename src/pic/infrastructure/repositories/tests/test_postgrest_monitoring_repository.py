"""Unit tests for PostgrestMonitoringRepository.

Mesmo padrão dos testes do repositório geospatial: httpx.MockTransport +
fake PostgREST que aplica os filtros básicos (eq/in/order/limit) sobre linhas
em memória — sem rede nem Redis reais.

Coverage:
    - fetch_group_series: âncora do grupo, filtros, parse, ordem
    - fetch_motivos: filtro de semana/status, ordenação por qtd
    - fetch_protocol_series: parse das métricas + descrição/secretaria
    - fetch_protocols_summary: parse + ordenação + filtro de secretaria
    - fetch_latest_week: ordem desc + limit 1
    - fetch_filter_options: opções com contagens, rótulo de cohort pt-BR
    - cache keys: determinísticas, variam por usuário/filtros
    - cache hit/miss
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.pic.domain.models.monitoring import (
    MonitoringFilterOptions,
    MonitoringFilters,
)
from src.pic.infrastructure.postgrest_client.client import PostgrestClient
from src.pic.infrastructure.postgrest_client.config import PostgrestClientConfig
from src.pic.infrastructure.repositories.postgrest_monitoring_repository import (
    PostgrestMonitoringRepository,
    _cohort_label,
    _make_group_key,
    _make_latest_week_key,
    _make_motivos_key,
    _make_protocols_key,
    _make_series_key,
)

CONFIG = PostgrestClientConfig(
    base_url="https://data-proxy.example/",
    schema="app_pequenos_cariocas",
    token_url="https://keycloak.example/token",
    client_id="pic-client",
    client_secret="pic-secret",
)


def _row(**overrides):
    row = {
        "data_referencia_semana_inicio": "2026-10-26",
        "data_referencia_semanal": "2026-11-01",
        "protocolo_id": "smas_cadunico_atualizado",
        "protocolo_descricao": "CadÚnico atualizado",
        "protocolo_secretaria": "SMAS",
        "pic_status": "Ativo",
        "pic_status_inativo_motivo": None,
        "pic_grupo": "Criança",
        "pic_cohort": "2025-03-01",
        "has_bolsa_familia": True,
        "bairro": "Centro",
        "qtd": 10,
        "regular": 8,
        "atencao": 1,
        "nao_priorizado": 0,
        "irregular": 1,
        "outros": 0,
        "nao_aplica": 0,
    }
    row.update(overrides)
    return row


class FakeMonitoringDataProxy:
    """Fake PostgREST que aplica eq/in/order/limit sobre linhas em memória."""

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
        path = request.url.path.lstrip("/")
        table = path.split(".")[-1]
        rows = [dict(r) for r in self.rows_by_table.get(table, [])]
        params = dict(request.url.params)

        for key, value in params.items():
            if value.startswith("eq."):
                target = value[3:]
                rows = [r for r in rows if str(r.get(key)) == target]
            elif value.startswith("in."):
                targets = value[3:].strip("()").split(",")
                rows = [r for r in rows if str(r.get(key)) in targets]
            elif key == "order":
                col, direction = value.rsplit(".", 1)
                rows.sort(key=lambda r: r.get(col), reverse=(direction == "desc"))

        limit = params.get("limit")
        if limit is not None:
            rows = rows[: int(limit)]

        return httpx.Response(200, json=rows, request=request)


def _make_repo(
    rows_by_table: dict[str, list[dict]],
    redis_client=None,
) -> tuple[PostgrestMonitoringRepository, FakeMonitoringDataProxy]:
    fake = FakeMonitoringDataProxy(rows_by_table)
    client = PostgrestClient(CONFIG, transport=httpx.MockTransport(fake))
    return PostgrestMonitoringRepository(client, redis_client=redis_client), fake


def _make_redis(cached: object | None = None) -> MagicMock:
    redis = MagicMock()
    if cached is None:
        redis.get = AsyncMock(return_value=None)
    else:
        redis.get = AsyncMock(return_value=json.dumps(cached).encode())
    redis.set = AsyncMock()
    return redis


_TABLE = "endpoint_participante_visao_geral_semanal_protocolos"


# ---------------------------------------------------------------------------
# Tests: fetch_group_series
# ---------------------------------------------------------------------------


class TestFetchGroupSeries:
    @pytest.mark.asyncio
    async def test_parses_rows_and_keeps_order(self):
        rows = [
            _row(data_referencia_semana_inicio="2026-10-19", pic_status="Ativo", qtd=5),
            _row(
                data_referencia_semana_inicio="2026-10-19", pic_status="Inativo", qtd=2
            ),
            _row(data_referencia_semana_inicio="2026-10-26", pic_status="Ativo", qtd=6),
        ]
        repo, _ = _make_repo({_TABLE: rows})
        result = await repo.fetch_group_series(MonitoringFilters())
        assert len(result) == 3
        assert result[0].week_start == "2026-10-19"
        assert result[0].status == "Ativo"
        assert result[0].qtd == 5
        assert result[2].week_start == "2026-10-26"

    @pytest.mark.asyncio
    async def test_uses_anchor_protocol(self):
        repo, fake = _make_repo({_TABLE: []})
        await repo.fetch_group_series(MonitoringFilters())
        data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
        params = dict(data_reqs[0].url.params)
        assert params.get("protocolo_id") == "eq.smas_cadunico_atualizado"

    @pytest.mark.asyncio
    async def test_applies_filters(self):
        repo, fake = _make_repo({_TABLE: []})
        await repo.fetch_group_series(
            MonitoringFilters(
                grupo=["Criança"],
                cohort=["2025-03-01"],
                status=["Ativo"],
                has_bolsa_familia=True,
                camada="bairro",
                regiao=["Centro"],
            )
        )
        data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
        params = dict(data_reqs[0].url.params)
        assert params.get("pic_grupo") == "in.(Criança)"
        assert params.get("pic_cohort") == "in.(2025-03-01)"
        assert params.get("pic_status") == "in.(Ativo)"
        assert params.get("has_bolsa_familia") == "eq.True"
        assert params.get("bairro") == "in.(Centro)"

    @pytest.mark.asyncio
    async def test_applies_multiple_regions_as_in(self):
        """Multiselect do mapa: as regiões viram ``in`` (OR) na coluna da
        camada, na ordem em que foram passadas (o use case já entrega a
        lista ordenada)."""
        repo, fake = _make_repo({_TABLE: []})
        await repo.fetch_group_series(
            MonitoringFilters(camada="bairro", regiao=["Copacabana", "Centro"])
        )
        data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
        params = dict(data_reqs[0].url.params)
        assert params.get("bairro") == "in.(Copacabana,Centro)"

    @pytest.mark.asyncio
    async def test_cache_hit_skips_postgrest(self):
        cached = [
            {
                "week_start": "2026-10-26",
                "snapshot_date": "2026-11-01",
                "status": "Ativo",
                "qtd": 7,
            }
        ]
        repo, fake = _make_repo({_TABLE: []}, redis_client=_make_redis(cached))
        result = await repo.fetch_group_series(MonitoringFilters())
        assert len(result) == 1
        assert result[0].qtd == 7
        data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
        assert data_reqs == []


# ---------------------------------------------------------------------------
# Tests: fetch_motivos
# ---------------------------------------------------------------------------


class TestFetchMotivos:
    @pytest.mark.asyncio
    async def test_parses_sorts_and_filters_week(self):
        rows = [
            _row(pic_status="Inativo", pic_status_inativo_motivo="motivo a", qtd=2),
            _row(pic_status="Inativo", pic_status_inativo_motivo="motivo b", qtd=9),
            _row(pic_status="Inativo", pic_status_inativo_motivo=None, qtd=1),
        ]
        repo, _ = _make_repo({_TABLE: rows})
        result = await repo.fetch_motivos("2026-10-26", MonitoringFilters())
        assert [m.motivo for m in result] == ["motivo b", "motivo a", None]
        assert result[0].qtd == 9

    @pytest.mark.asyncio
    async def test_applies_week_status_and_anchor(self):
        repo, fake = _make_repo({_TABLE: []})
        await repo.fetch_motivos("2026-10-26", MonitoringFilters())
        data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
        params = dict(data_reqs[0].url.params)
        assert params.get("data_referencia_semana_inicio") == "eq.2026-10-26"
        assert params.get("pic_status") == "eq.Inativo"
        assert params.get("protocolo_id") == "eq.smas_cadunico_atualizado"


# ---------------------------------------------------------------------------
# Tests: fetch_protocol_series
# ---------------------------------------------------------------------------


class TestFetchProtocolSeries:
    @pytest.mark.asyncio
    async def test_parses_metrics(self):
        rows = [
            _row(
                protocolo_id="sme_frequencia_escolar",
                protocolo_descricao="Frequência escolar",
                protocolo_secretaria="SME",
                pic_status="Ativo",
                qtd=10,
                regular=7,
                atencao=1,
                irregular=2,
                nao_aplica=3,
            )
        ]
        repo, _ = _make_repo({_TABLE: rows})
        result = await repo.fetch_protocol_series(
            "sme_frequencia_escolar", MonitoringFilters()
        )
        assert len(result) == 1
        row = result[0]
        assert row.protocolo_descricao == "Frequência escolar"
        assert row.protocolo_secretaria == "SME"
        assert row.regular == 7
        assert row.atencao == 1
        assert row.irregular == 2
        assert row.nao_aplica == 3

    @pytest.mark.asyncio
    async def test_applies_protocol_and_filters(self):
        repo, fake = _make_repo({_TABLE: []})
        await repo.fetch_protocol_series(
            "sms_vacinacao_pentavalente",
            MonitoringFilters(grupo=["Gestante"]),
        )
        data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
        params = dict(data_reqs[0].url.params)
        assert params.get("protocolo_id") == "eq.sms_vacinacao_pentavalente"
        assert params.get("pic_grupo") == "in.(Gestante)"

    @pytest.mark.asyncio
    async def test_geral_filters_nivel_and_geral_keys(self):
        """Regularidade geral: linhas nivel/protocolo_id/protocolo_secretaria
        = 'geral' — o número geral consolidado."""
        rows = [
            _row(
                protocolo_id="geral",
                protocolo_descricao="geral",
                protocolo_secretaria="geral",
                nivel="geral",
                pic_status="Ativo",
                qtd=100,
                regular=50,
            )
        ]
        repo, fake = _make_repo({_TABLE: rows})
        result = await repo.fetch_protocol_series("geral", MonitoringFilters())
        data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
        params = dict(data_reqs[0].url.params)
        assert params.get("protocolo_id") == "eq.geral"
        assert params.get("protocolo_secretaria") == "eq.geral"
        assert params.get("nivel") == "eq.geral"
        assert len(result) == 1
        assert result[0].regular == 50


# ---------------------------------------------------------------------------
# Tests: fetch_protocols_summary
# ---------------------------------------------------------------------------


class TestFetchProtocolsSummary:
    @pytest.mark.asyncio
    async def test_parses_and_sorts_by_secretaria_descricao(self):
        rows = [
            _row(protocolo_id="b", protocolo_secretaria="SMS", protocolo_descricao="B"),
            _row(protocolo_id="a", protocolo_secretaria="SME", protocolo_descricao="A"),
            _row(protocolo_id="c", protocolo_secretaria="SME", protocolo_descricao="C"),
        ]
        repo, _ = _make_repo({_TABLE: rows})
        result = await repo.fetch_protocols_summary(
            "2026-10-26", None, MonitoringFilters()
        )
        assert [r.protocolo_id for r in result] == ["a", "c", "b"]
        assert result[0].snapshot_date == "2026-11-01"

    @pytest.mark.asyncio
    async def test_applies_week_and_secretaria(self):
        repo, fake = _make_repo({_TABLE: []})
        await repo.fetch_protocols_summary("2026-10-26", "SMS", MonitoringFilters())
        data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
        params = dict(data_reqs[0].url.params)
        assert params.get("data_referencia_semana_inicio") == "eq.2026-10-26"
        assert params.get("protocolo_secretaria") == "eq.SMS"

    @pytest.mark.asyncio
    async def test_excludes_geral_row(self):
        """A tabela "todos os protocolos" não lista a linha nivel='geral'."""
        rows = [
            _row(
                protocolo_id="geral",
                protocolo_descricao="geral",
                protocolo_secretaria="geral",
            ),
            _row(protocolo_id="a", protocolo_secretaria="SME", protocolo_descricao="A"),
        ]
        repo, _ = _make_repo({_TABLE: rows})
        result = await repo.fetch_protocols_summary(
            "2026-10-26", None, MonitoringFilters()
        )
        assert [r.protocolo_id for r in result] == ["a"]


# ---------------------------------------------------------------------------
# Tests: fetch_latest_week
# ---------------------------------------------------------------------------


class TestFetchLatestWeek:
    @pytest.mark.asyncio
    async def test_returns_max_week(self):
        rows = [
            _row(data_referencia_semana_inicio="2026-10-19"),
            _row(data_referencia_semana_inicio="2026-10-26"),
        ]
        repo, _ = _make_repo({_TABLE: rows})
        result = await repo.fetch_latest_week(MonitoringFilters())
        assert result == "2026-10-26"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_rows(self):
        repo, _ = _make_repo({_TABLE: []})
        result = await repo.fetch_latest_week(MonitoringFilters())
        assert result is None


# ---------------------------------------------------------------------------
# Tests: fetch_filter_options
# ---------------------------------------------------------------------------


class TestFetchFilterOptions:
    @pytest.mark.asyncio
    async def test_builds_options_with_counts(self):
        rows = [
            _row(
                data_referencia_semana_inicio="2026-10-26",
                pic_grupo="Criança",
                pic_cohort="2025-03-01",
                qtd=100,
            ),
            _row(
                data_referencia_semana_inicio="2026-10-26",
                pic_grupo="Gestante",
                pic_cohort="2026-07-01",
                pic_status="Inativo",
                qtd=50,
            ),
        ]
        repo, _ = _make_repo({_TABLE: rows})
        result = await repo.fetch_filter_options()
        assert isinstance(result, MonitoringFilterOptions)
        # (o GROUP BY por pic_grupo é feito pelo PostgREST; o repositório só
        # parseia as linhas já agregadas — por isso grupos distintos aqui)
        assert [(g.value, g.count) for g in result.grupos] == [
            ("Criança", 100),
            ("Gestante", 50),
        ]
        cohort_labels = {c.label for c in result.cohorts}
        assert "Mar/2025" in cohort_labels
        assert "Jul/2026" in cohort_labels

    @pytest.mark.asyncio
    async def test_cohort_label_pt_br(self):
        assert _cohort_label("2025-03-01") == "Mar/2025"
        assert _cohort_label("2026-11-01") == "Nov/2026"
        assert _cohort_label("malformado") == "malformado"

    @pytest.mark.asyncio
    async def test_excludes_geral_from_protocol_list(self):
        """A linha nivel='geral' não vira opção de protocolo nem secretaria."""
        rows = [
            _row(),
            _row(
                protocolo_id="geral",
                protocolo_descricao="geral",
                protocolo_secretaria="geral",
            ),
        ]
        repo, _ = _make_repo({_TABLE: rows})
        result = await repo.fetch_filter_options()
        assert [p.id for p in result.protocolos] == ["smas_cadunico_atualizado"]
        assert "geral" not in result.secretarias

    @pytest.mark.asyncio
    async def test_cache_hit_skips_postgrest(self):
        cached = {
            "grupos": [{"value": "Criança", "label": "Criança", "count": 10}],
            "cohorts": [],
            "status": [],
            "protocolos": [],
            "secretarias": [],
        }
        repo, fake = _make_repo({_TABLE: []}, redis_client=_make_redis(cached))
        result = await repo.fetch_filter_options()
        assert result.grupos[0].value == "Criança"
        data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
        assert data_reqs == []

    @pytest.mark.asyncio
    async def test_empty_when_no_data(self):
        repo, _ = _make_repo({_TABLE: []})
        result = await repo.fetch_filter_options()
        assert result.grupos == []
        assert result.secretarias == []


# ---------------------------------------------------------------------------
# Tests: cache keys
# ---------------------------------------------------------------------------


class TestCacheKeys:
    def test_group_key_varies_by_user_and_filters(self):
        base = _make_group_key("cpf", MonitoringFilters())
        assert base != _make_group_key("outro", MonitoringFilters())
        assert base != _make_group_key("cpf", MonitoringFilters(grupo=["Criança"]))
        assert base == _make_group_key("cpf", MonitoringFilters())
        # Ordem da lista não altera a chave
        assert _make_group_key(
            "cpf", MonitoringFilters(grupo=["Criança", "Gestante"])
        ) == _make_group_key("cpf", MonitoringFilters(grupo=["Gestante", "Criança"]))
        # Mesmo para a seleção de regiões (OR)
        assert _make_group_key(
            "cpf", MonitoringFilters(camada="bairro", regiao=["A", "B"])
        ) == _make_group_key(
            "cpf", MonitoringFilters(camada="bairro", regiao=["B", "A"])
        )

    def test_motivos_key_varies_by_week(self):
        base = _make_motivos_key("cpf", "2026-10-26", MonitoringFilters())
        assert base != _make_motivos_key("cpf", "2026-10-19", MonitoringFilters())

    def test_series_key_varies_by_protocol(self):
        assert _make_series_key("cpf", "a", MonitoringFilters()) != (
            _make_series_key("cpf", "b", MonitoringFilters())
        )

    def test_protocols_key_varies_by_week_and_secretaria(self):
        base = _make_protocols_key("cpf", "2026-10-26", None, MonitoringFilters())
        assert base != _make_protocols_key(
            "cpf", "2026-10-19", None, MonitoringFilters()
        )
        assert base != _make_protocols_key(
            "cpf", "2026-10-26", "SMS", MonitoringFilters()
        )

    def test_latest_week_key_varies_by_user(self):
        assert _make_latest_week_key("cpf", MonitoringFilters()) != (
            _make_latest_week_key("outro", MonitoringFilters())
        )
