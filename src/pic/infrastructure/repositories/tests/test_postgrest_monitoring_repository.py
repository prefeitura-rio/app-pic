"""Unit tests for PostgrestMonitoringRepository.

Mesmo padrão dos testes do repositório geospatial: httpx.MockTransport +
fake PostgREST que aplica os filtros básicos (eq/in/order/limit) sobre linhas
em memória — sem rede nem Redis reais.

Coverage:
    - fetch_protocol_series: parse das métricas + descrição/secretaria,
      filtros, multiselect de regiões (in/OR), pseudo-protocolo "geral"
    - cache keys: determinísticas, variam por usuário/filtros; camada sem
      região não entra na chave
    - cache hit/miss
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.pic.domain.models.monitoring import MonitoringFilters
from src.pic.infrastructure.postgrest_client.client import PostgrestClient
from src.pic.infrastructure.postgrest_client.config import PostgrestClientConfig
from src.pic.infrastructure.repositories.postgrest_monitoring_repository import (
    PostgrestMonitoringRepository,
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


def _data_params(fake: FakeMonitoringDataProxy) -> dict[str, str]:
    data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
    assert len(data_reqs) == 1
    return dict(data_reqs[0].url.params)


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
        params = _data_params(fake)
        assert params.get("protocolo_id") == "eq.sms_vacinacao_pentavalente"
        assert params.get("pic_grupo") == "in.(Gestante)"

    @pytest.mark.asyncio
    async def test_applies_multiple_regions_as_in(self):
        """Multiselect do mapa: as regiões viram ``in`` (OR) na coluna da
        camada, na ordem em que foram passadas (o use case já entrega a
        lista ordenada)."""
        repo, fake = _make_repo({_TABLE: []})
        await repo.fetch_protocol_series(
            "x", MonitoringFilters(camada="bairro", regiao=["Copacabana", "Centro"])
        )
        params = _data_params(fake)
        assert params.get("bairro") == "in.(Copacabana,Centro)"

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
        params = _data_params(fake)
        assert params.get("protocolo_id") == "eq.geral"
        assert params.get("protocolo_secretaria") == "eq.geral"
        assert params.get("nivel") == "eq.geral"
        assert len(result) == 1
        assert result[0].regular == 50

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
        result = await repo.fetch_protocol_series("x", MonitoringFilters())
        assert len(result) == 1
        assert result[0].qtd == 7
        data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
        assert data_reqs == []


# ---------------------------------------------------------------------------
# Tests: cache keys
# ---------------------------------------------------------------------------


class TestCacheKeys:
    def test_series_key_varies_by_user_protocol_and_filters(self):
        base = _make_series_key("cpf", "a", MonitoringFilters())
        assert base != _make_series_key("outro", "a", MonitoringFilters())
        assert base != _make_series_key("cpf", "b", MonitoringFilters())
        assert base != _make_series_key("cpf", "a", MonitoringFilters(grupo=["Criança"]))
        assert base == _make_series_key("cpf", "a", MonitoringFilters())
        # Ordem da lista não altera a chave
        assert _make_series_key(
            "cpf", "a", MonitoringFilters(grupo=["Criança", "Gestante"])
        ) == _make_series_key("cpf", "a", MonitoringFilters(grupo=["Gestante", "Criança"]))
        # Mesmo para a seleção de regiões (OR)
        assert _make_series_key(
            "cpf", "a", MonitoringFilters(camada="bairro", regiao=["A", "B"])
        ) == _make_series_key(
            "cpf", "a", MonitoringFilters(camada="bairro", regiao=["B", "A"])
        )

    def test_camada_without_regiao_does_not_change_key(self):
        """Sem região a série é da cidade inteira — trocar a camada não pode
        gerar chave (e cache) diferente."""
        assert _make_series_key("cpf", "a", MonitoringFilters(camada="bairro")) == (
            _make_series_key("cpf", "a", MonitoringFilters(camada="ra"))
        )
