"""E2E tests for the monitoring V2 endpoint (Acompanhamento).

Mesmo padrão do test_geospatial_e2e.py: ASGI test client, use case fake
(sem PostgREST/Redis), autenticação sobrescrita. Cobre roteamento, parsing
de query params, repasse do token e mapeamento de erros.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from src.core.security.jwt import get_current_user_permissions_v2, verify_jwt
from src.core.security.permissions_models import UserPermissions
from src.main import app
from src.pic.domain.models.monitoring import (
    MonitoringFilters,
    MonitoringMeta,
    MonitoringSeriesOutput,
    ProtocolOption,
    ProtocolPoint,
)
from src.pic.infrastructure.postgrest_client.errors import PostgrestError
from src.pic.presentation.di import get_monitoring_protocol_series_use_case

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeSeriesUseCase:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.received: dict = {}

    async def execute(
        self,
        protocolo_id,
        filters,
        permissions=None,
        user_token=None,
        user_id=None,
        bypass_cache=False,
    ):
        self.received = {
            "protocolo_id": protocolo_id,
            "filters": filters,
            "user_token": user_token,
            "user_id": user_id,
            "bypass_cache": bypass_cache,
        }
        if self.error:
            raise self.error
        return MonitoringSeriesOutput(
            protocolo=ProtocolOption(id=protocolo_id, secretaria="SMS"),
            meta=MonitoringMeta(has_data=True),
            series=[ProtocolPoint(week_start="2026-11-01", total=5)],
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def override_auth():
    app.dependency_overrides[verify_jwt] = lambda: {"preferred_username": "00000000000"}
    app.dependency_overrides[get_current_user_permissions_v2] = lambda: UserPermissions(
        cpf="00000000000",
        is_admin=True,
        is_super_admin=True,
        secretarias_acesso=["SME", "SMS", "SMAS"],
    )
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def series_use_case():
    return FakeSeriesUseCase()


@pytest.fixture
def override_use_cases(series_use_case):
    app.dependency_overrides[get_monitoring_protocol_series_use_case] = (
        lambda: series_use_case
    )
    yield
    app.dependency_overrides.clear()


@pytest.fixture
async def client(override_auth, override_use_cases):
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={
            "Authorization": "Bearer fake-jwt-token",
            "X-Access-Token": "fake-access-token",
        },
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Tests: GET /api/v2/monitoring/series
# ---------------------------------------------------------------------------


class TestGetMonitoringSeries:
    @pytest.mark.asyncio
    async def test_returns_200(self, client):
        resp = await client.get(
            "/api/v2/monitoring/series?protocolo=sms_vacinacao_pentavalente"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["protocolo"]["id"] == "sms_vacinacao_pentavalente"
        assert body["series"][0]["total"] == 5

    @pytest.mark.asyncio
    async def test_protocolo_required(self, client):
        resp = await client.get("/api/v2/monitoring/series")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_geral_forwarded(self, client, series_use_case):
        """'geral' é aceito como pseudo-protocolo (regularidade geral)."""
        resp = await client.get("/api/v2/monitoring/series?protocolo=geral")
        assert resp.status_code == 200
        assert series_use_case.received["protocolo_id"] == "geral"

    @pytest.mark.asyncio
    async def test_filters_forwarded(self, client, series_use_case):
        await client.get(
            "/api/v2/monitoring/series?protocolo=p1&grupo=Criança"
            "&has_bolsa_familia=false&camada=ra&regiao=Rio%20Comprido"
        )
        assert series_use_case.received["protocolo_id"] == "p1"
        filters: MonitoringFilters = series_use_case.received["filters"]
        assert filters.grupo == ["Criança"]
        assert filters.has_bolsa_familia is False
        assert filters.camada == "ra"
        assert filters.regiao == ["Rio Comprido"]

    @pytest.mark.asyncio
    async def test_multiple_regioes_forwarded(self, client, series_use_case):
        """Multiselect do mapa: repetir `regiao` gera a lista (OR)."""
        await client.get(
            "/api/v2/monitoring/series?protocolo=p1"
            "&camada=bairro&regiao=Centro&regiao=Copacabana"
        )
        filters: MonitoringFilters = series_use_case.received["filters"]
        assert filters.regiao == ["Centro", "Copacabana"]

    @pytest.mark.asyncio
    async def test_user_id_forwarded(self, client, series_use_case):
        await client.get("/api/v2/monitoring/series?protocolo=p1")
        assert series_use_case.received["user_id"] == "00000000000"

    @pytest.mark.asyncio
    async def test_x_access_token_forwarded(self, client, series_use_case):
        await client.get("/api/v2/monitoring/series?protocolo=p1")
        assert series_use_case.received["user_token"] == "fake-access-token"

    @pytest.mark.asyncio
    async def test_bypass_cache_forwarded(self, client, series_use_case):
        await client.get("/api/v2/monitoring/series?protocolo=p1&bypass_cache=true")
        assert series_use_case.received["bypass_cache"] is True

    @pytest.mark.asyncio
    async def test_maps_postgrest_error_to_502(self, override_auth):
        app.dependency_overrides[get_monitoring_protocol_series_use_case] = (
            lambda: FakeSeriesUseCase(error=PostgrestError("boom", code="P0001"))
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Authorization": "Bearer fake-jwt-token"},
        ) as ac:
            resp = await ac.get("/api/v2/monitoring/series?protocolo=p1")
        assert resp.status_code == 502
        assert resp.json()["detail"] == "boom"

    @pytest.mark.asyncio
    async def test_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/v2/monitoring/series?protocolo=p1")
        assert resp.status_code in (401, 403)
