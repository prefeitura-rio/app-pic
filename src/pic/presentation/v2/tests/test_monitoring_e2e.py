"""E2E tests for the monitoring V2 endpoints (Acompanhamento).

Mesmo padrão do test_geospatial_e2e.py: ASGI test client, use cases fakes
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
    GroupPoint,
    MonitoringFilterOptions,
    MonitoringFilters,
    MonitoringGroupOutput,
    MonitoringMeta,
    MonitoringOption,
    MonitoringProtocolsOutput,
    MonitoringSeriesOutput,
    MotivoInativo,
    ProtocolOption,
    ProtocolPoint,
    ProtocolSummary,
)
from src.pic.infrastructure.postgrest_client.errors import PostgrestError
from src.pic.presentation.di import (
    get_monitoring_filters_use_case,
    get_monitoring_group_use_case,
    get_monitoring_protocol_series_use_case,
    get_monitoring_protocols_use_case,
)

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeFiltersUseCase:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.received: dict = {}

    async def execute(self, user_token=None, bypass_cache=False):
        self.received = {"user_token": user_token, "bypass_cache": bypass_cache}
        if self.error:
            raise self.error
        return MonitoringFilterOptions(
            grupos=[MonitoringOption(value="Criança", label="Criança", count=100)],
            cohorts=[MonitoringOption(value="2025-03-01", label="Mar/2025", count=50)],
            status=[MonitoringOption(value="Ativo", label="Ativo", count=80)],
            protocolos=[
                ProtocolOption(
                    id="sme_frequencia_escolar",
                    descricao="Frequência escolar",
                    secretaria="SME",
                )
            ],
            secretarias=["SME"],
        )


class FakeGroupUseCase:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.received: dict = {}

    async def execute(
        self,
        filters,
        permissions=None,
        user_token=None,
        user_id=None,
        bypass_cache=False,
    ):
        self.received = {
            "filters": filters,
            "permissions": permissions,
            "user_token": user_token,
            "user_id": user_id,
            "bypass_cache": bypass_cache,
        }
        if self.error:
            raise self.error
        return MonitoringGroupOutput(
            meta=MonitoringMeta(has_data=True, weeks_count=35),
            series=[GroupPoint(week_start="2026-11-01", total=10)],
            motivos=[MotivoInativo(motivo="motivo", total=2)],
        )


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


class FakeProtocolsUseCase:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.received: dict = {}

    async def execute(
        self,
        filters,
        permissions=None,
        user_token=None,
        user_id=None,
        bypass_cache=False,
        week_start=None,
        secretaria=None,
    ):
        self.received = {
            "filters": filters,
            "user_token": user_token,
            "user_id": user_id,
            "bypass_cache": bypass_cache,
            "week_start": week_start,
            "secretaria": secretaria,
        }
        if self.error:
            raise self.error
        return MonitoringProtocolsOutput(
            week_start=week_start or "2026-11-01",
            snapshot_date="2026-11-03",
            protocols=[
                ProtocolSummary(
                    protocolo_id="sme_frequencia_escolar",
                    protocolo_descricao="Frequência escolar",
                    protocolo_secretaria="SME",
                    total=100,
                    regular_total=91,
                )
            ],
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
def filters_use_case():
    return FakeFiltersUseCase()


@pytest.fixture
def group_use_case():
    return FakeGroupUseCase()


@pytest.fixture
def series_use_case():
    return FakeSeriesUseCase()


@pytest.fixture
def protocols_use_case():
    return FakeProtocolsUseCase()


@pytest.fixture
def override_use_cases(
    filters_use_case, group_use_case, series_use_case, protocols_use_case
):
    app.dependency_overrides[get_monitoring_filters_use_case] = lambda: filters_use_case
    app.dependency_overrides[get_monitoring_group_use_case] = lambda: group_use_case
    app.dependency_overrides[get_monitoring_protocol_series_use_case] = (
        lambda: series_use_case
    )
    app.dependency_overrides[get_monitoring_protocols_use_case] = (
        lambda: protocols_use_case
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
# Tests: GET /api/v2/monitoring/filters
# ---------------------------------------------------------------------------


class TestGetMonitoringFilters:
    @pytest.mark.asyncio
    async def test_returns_200_with_options(self, client, filters_use_case):
        resp = await client.get("/api/v2/monitoring/filters")
        assert resp.status_code == 200
        body = resp.json()
        assert body["secretarias"] == ["SME"]
        assert body["grupos"][0]["value"] == "Criança"
        assert body["cohorts"][0]["label"] == "Mar/2025"

    @pytest.mark.asyncio
    async def test_x_access_token_forwarded(self, client, filters_use_case):
        await client.get("/api/v2/monitoring/filters")
        assert filters_use_case.received["user_token"] == "fake-access-token"

    @pytest.mark.asyncio
    async def test_bypass_cache_forwarded(self, client, filters_use_case):
        await client.get("/api/v2/monitoring/filters?bypass_cache=true")
        assert filters_use_case.received["bypass_cache"] is True

    @pytest.mark.asyncio
    async def test_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/v2/monitoring/filters")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Tests: GET /api/v2/monitoring/group
# ---------------------------------------------------------------------------


class TestGetMonitoringGroup:
    @pytest.mark.asyncio
    async def test_returns_200(self, client):
        resp = await client.get("/api/v2/monitoring/group")
        assert resp.status_code == 200
        body = resp.json()
        assert body["can_view_monitoring"] is True
        assert body["meta"]["weeks_count"] == 35
        assert body["series"][0]["week_start"] == "2026-11-01"
        assert body["motivos"][0]["motivo"] == "motivo"

    @pytest.mark.asyncio
    async def test_filters_multiselect_forwarded(self, client, group_use_case):
        resp = await client.get(
            "/api/v2/monitoring/group?grupo=Criança&grupo=Gestante"
            "&cohort=2025-03-01&status=Ativo&has_bolsa_familia=true"
        )
        assert resp.status_code == 200
        filters: MonitoringFilters = group_use_case.received["filters"]
        assert filters.grupo == ["Criança", "Gestante"]
        assert filters.cohort == ["2025-03-01"]
        assert filters.status == ["Ativo"]
        assert filters.has_bolsa_familia is True
        assert filters.camada is None

    @pytest.mark.asyncio
    async def test_camada_regiao_forwarded(self, client, group_use_case):
        await client.get("/api/v2/monitoring/group?camada=bairro&regiao=Centro")
        filters: MonitoringFilters = group_use_case.received["filters"]
        assert filters.camada == "bairro"
        assert filters.regiao == ["Centro"]

    @pytest.mark.asyncio
    async def test_multiple_regioes_forwarded(self, client, group_use_case):
        """Multiselect do mapa: repetir `regiao` gera a lista (OR)."""
        await client.get(
            "/api/v2/monitoring/group?camada=bairro&regiao=Centro&regiao=Copacabana"
        )
        filters: MonitoringFilters = group_use_case.received["filters"]
        assert filters.regiao == ["Centro", "Copacabana"]

    @pytest.mark.asyncio
    async def test_user_id_forwarded(self, client, group_use_case):
        await client.get("/api/v2/monitoring/group")
        assert group_use_case.received["user_id"] == "00000000000"

    @pytest.mark.asyncio
    async def test_maps_postgrest_error_to_502(self, override_auth):
        app.dependency_overrides[get_monitoring_group_use_case] = (
            lambda: FakeGroupUseCase(error=PostgrestError("boom", code="P0001"))
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Authorization": "Bearer fake-jwt-token"},
        ) as ac:
            resp = await ac.get("/api/v2/monitoring/group")
        assert resp.status_code == 502
        assert resp.json()["detail"] == "boom"


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


# ---------------------------------------------------------------------------
# Tests: GET /api/v2/monitoring/protocols
# ---------------------------------------------------------------------------


class TestGetMonitoringProtocols:
    @pytest.mark.asyncio
    async def test_returns_200(self, client):
        resp = await client.get("/api/v2/monitoring/protocols")
        assert resp.status_code == 200
        body = resp.json()
        assert body["week_start"] == "2026-11-01"
        assert body["snapshot_date"] == "2026-11-03"
        assert body["protocols"][0]["regular_total"] == 91

    @pytest.mark.asyncio
    async def test_week_and_secretaria_forwarded(self, client, protocols_use_case):
        await client.get(
            "/api/v2/monitoring/protocols?week_start=2026-10-26&secretaria=SMS"
        )
        assert protocols_use_case.received["week_start"] == "2026-10-26"
        assert protocols_use_case.received["secretaria"] == "SMS"

    @pytest.mark.asyncio
    async def test_invalid_week_start_returns_422(self, client):
        resp = await client.get("/api/v2/monitoring/protocols?week_start=2026-13-99")
        assert resp.status_code == 422
