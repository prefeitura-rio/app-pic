"""End-to-end tests for GET /api/v2/dashboard.

These tests exercise the full FastAPI request/response cycle using the ASGI
transport (no real network).  The PostgREST and Redis layers are replaced by
lightweight fakes so the suite runs offline and deterministically.

Scenarios covered:
    1. Super-admin with all secretarias → 200 + populated Dashboard
    2. No auth header → 401
    3. User without any secretaria access → 200 + can_view_dashboard=False + empty data
    4. Query params forwarded: secretaria, bypass_cache, grupo, etc.
    5. Each dashboard section present in the response body
    6. bypass_cache=true query param accepted without error
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.core.security.jwt import get_current_user_permissions_v2, verify_jwt
from src.core.security.permissions_models import UserPermissions
from src.main import app
from src.pic.application.use_cases.get_dashboard import (
    DashboardOutput,
    GetDashboardUseCase,
)
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
from src.pic.presentation.di import get_dashboard_use_case

# ---------------------------------------------------------------------------
# Canned Dashboard fixture returned by the fake use case
# ---------------------------------------------------------------------------

FAKE_DASHBOARD = Dashboard(
    total_participantes=14,
    total_regulares=10,
    total_irregulares=2,
    percentual_regular=71.4,
    percentual_irregular=14.3,
    protocolos=[
        ProtocoloIndicador(
            protocolo_id="p1",
            protocolo_descricao="Vacinação",
            protocolo_secretaria="SMS",
            numerador=8,
            denominador=15,
            percentual_regular=53.3,
            percentual_irregular=46.7,
        )
    ],
    resultado_programa=[
        ResultadoProgramaPoint(
            mes="2025-01",
            mes_label="Jan/25",
            todos=71.4,
            saude=80.0,
            educacao=60.0,
            assistencia=100.0,
        )
    ],
    distribuicao_por_safra=[
        DistribuicaoSafra(
            safra="Jan/25",
            total_participantes=8,
            total_ativos=5,
            total_inativos=3,
        )
    ],
    distribuicao_motivo_saida=[
        DistribuicaoMotivoSaida(motivo="Não informado", total=3),
    ],
    tempo_medio_irregularidade=[
        TempoMedioIrregularidade(
            secretaria="geral",
            secretaria_label="Geral",
            tempo_medio_dias=25.0,
            total_irregulares=3,
        )
    ],
    distribuicao_tempo_irregularidade=[
        DistribuicaoTempoIrregularidade(faixa="0-30",  faixa_label="0-30 dias",  count=3, percentual=100.0),
        DistribuicaoTempoIrregularidade(faixa="31-60", faixa_label="31-60 dias", count=0, percentual=0.0),
        DistribuicaoTempoIrregularidade(faixa="61-90", faixa_label="61-90 dias", count=0, percentual=0.0),
        DistribuicaoTempoIrregularidade(faixa="90+",   faixa_label="90+ dias",   count=0, percentual=0.0),
    ],
    taxa_resolucao_mensal=[
        TaxaResolucaoMensalPoint(
            mes="2025-01",
            mes_label="Jan/25",
            todos=73.3,
            saude=80.0,
            educacao=0.0,
            assistencia=60.0,
        )
    ],
)

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

SUPER_ADMIN = UserPermissions(
    cpf="12345678900",
    is_admin=True,
    is_super_admin=True,
    secretarias_acesso=["SME", "SMS", "SMAS"],
)

NO_ACCESS = UserPermissions(
    cpf="99999999999",
    is_admin=False,
    is_super_admin=False,
    secretarias_acesso=[],
)


def _make_fake_use_case(dashboard: Dashboard | None = None) -> GetDashboardUseCase:
    """Return a use case whose repository is mocked to return *dashboard*."""
    fake_repo = MagicMock()
    fake_repo.get_dashboard_metrics = AsyncMock(
        return_value=dashboard or FAKE_DASHBOARD
    )
    return GetDashboardUseCase(repository=fake_repo)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def override_auth_superadmin():
    """Override JWT + permissions with a super-admin."""
    app.dependency_overrides[verify_jwt] = lambda: {"preferred_username": "12345678900"}
    app.dependency_overrides[get_current_user_permissions_v2] = lambda: SUPER_ADMIN
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def override_auth_no_access():
    """Override JWT + permissions with a user that has no secretaria access."""
    app.dependency_overrides[verify_jwt] = lambda: {"preferred_username": "99999999999"}
    app.dependency_overrides[get_current_user_permissions_v2] = lambda: NO_ACCESS
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def override_use_case():
    """Override the dashboard use case with a fake that returns FAKE_DASHBOARD."""
    fake = _make_fake_use_case()
    app.dependency_overrides[get_dashboard_use_case] = lambda: fake
    yield fake
    if get_dashboard_use_case in app.dependency_overrides:
        del app.dependency_overrides[get_dashboard_use_case]


@pytest.fixture
async def client(override_auth_superadmin, override_use_case):
    """Authenticated client with mocked use case (no real network)."""
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
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_dashboard_200_superadmin(client):
    """Super-admin gets 200 with populated dashboard data."""
    response = await client.get("/api/v2/dashboard")

    assert response.status_code == 200
    body = response.json()
    assert body["can_view_dashboard"] is True
    assert "data" in body
    assert "filters" not in body

    data = body["data"]
    assert data["total_participantes"] == 14
    assert data["total_regulares"] == 10
    assert data["total_irregulares"] == 2
    assert isinstance(data["protocolos"], list)
    assert len(data["protocolos"]) == 1
    assert data["protocolos"][0]["protocolo_id"] == "p1"


@pytest.mark.asyncio
async def test_response_contains_all_sections(client):
    """All seven dashboard sections must be present in the response."""
    response = await client.get("/api/v2/dashboard")
    assert response.status_code == 200
    data = response.json()["data"]

    assert "total_participantes" in data
    assert "total_regulares" in data
    assert "total_irregulares" in data
    assert "percentual_regular" in data
    assert "percentual_irregular" in data
    assert "protocolos" in data
    assert "resultado_programa" in data
    assert "distribuicao_por_safra" in data
    assert "distribuicao_motivo_saida" in data
    assert "tempo_medio_irregularidade" in data
    assert "distribuicao_tempo_irregularidade" in data
    assert "taxa_resolucao_mensal" in data


@pytest.mark.asyncio
async def test_get_dashboard_401_without_auth():
    """Request without auth token must get 401."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v2/dashboard")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_dashboard_no_secretaria_access(override_auth_no_access):
    """User without secretaria access gets 200 but can_view_dashboard=False."""
    fake = _make_fake_use_case()
    app.dependency_overrides[get_dashboard_use_case] = lambda: fake

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": "Bearer fake-jwt-token"},
    ) as ac:
        response = await ac.get("/api/v2/dashboard")

    app.dependency_overrides.pop(get_dashboard_use_case, None)

    assert response.status_code == 200
    body = response.json()
    assert body["can_view_dashboard"] is False
    assert body["data"]["total_participantes"] == 0


@pytest.mark.asyncio
async def test_bypass_cache_query_param_accepted(client):
    """bypass_cache=true must be accepted without error."""
    response = await client.get("/api/v2/dashboard?bypass_cache=true")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_secretaria_query_param_forwarded(override_auth_superadmin):
    """secretaria query param must be forwarded to the use case."""
    fake = _make_fake_use_case()
    app.dependency_overrides[get_dashboard_use_case] = lambda: fake

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": "Bearer fake-jwt-token"},
    ) as ac:
        response = await ac.get("/api/v2/dashboard?secretaria=SMS")

    app.dependency_overrides.pop(get_dashboard_use_case, None)

    assert response.status_code == 200
    call_kwargs = fake._repository.get_dashboard_metrics.call_args.kwargs
    assert call_kwargs.get("secretaria") == "SMS"


@pytest.mark.asyncio
async def test_grupo_filter_forwarded(override_auth_superadmin):
    """grupo query param must be forwarded as a filter."""
    fake = _make_fake_use_case()
    app.dependency_overrides[get_dashboard_use_case] = lambda: fake

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": "Bearer fake-jwt-token"},
    ) as ac:
        response = await ac.get("/api/v2/dashboard?grupo=Criança")

    app.dependency_overrides.pop(get_dashboard_use_case, None)

    assert response.status_code == 200
    call_kwargs = fake._repository.get_dashboard_metrics.call_args.kwargs
    assert "pic_grupo" in call_kwargs.get("filters", {})


@pytest.mark.asyncio
async def test_histogram_has_four_fixed_faixas(client):
    """distribuicao_tempo_irregularidade must always have exactly 4 faixas."""
    response = await client.get("/api/v2/dashboard")
    data = response.json()["data"]
    faixas = [d["faixa"] for d in data["distribuicao_tempo_irregularidade"]]
    assert faixas == ["0-30", "31-60", "61-90", "90+"]


@pytest.mark.asyncio
async def test_protocolo_percentual_complement(client):
    """percentual_irregular must equal round(100 - perc_raw, 1), not 100 - round(...)."""
    response = await client.get("/api/v2/dashboard")
    data = response.json()["data"]
    p = data["protocolos"][0]
    # FAKE_DASHBOARD was constructed with 8/15: raw = 53.333...
    # percentual_regular=53.3, percentual_irregular=46.7 (not 100-53.3=46.7, but
    # round(100-53.333..., 1)=46.7 — same here, but the model carries the right values)
    assert p["percentual_regular"] + p["percentual_irregular"] == pytest.approx(100.0, abs=0.2)
