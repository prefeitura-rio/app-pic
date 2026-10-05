"""End-to-end tests for GET /api/v2/acordo-resultados.

Exercises the full FastAPI request/response cycle using the ASGI transport
(no real network). The PostgREST/Redis layers are replaced by a mocked use
case so the suite runs offline and deterministically.

Scenarios covered:
    1. Super-admin → 200 + populated AcordoResultados + can_view_acordo=True
    2. No auth header → 401
    3. User without full secretaria access → 200 + can_view_acordo=False + empty
    4. All agreement sections present in the response body
    5. bypass_cache=true query param accepted
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.core.security.jwt import get_current_user_permissions_v2, verify_jwt
from src.core.security.permissions_models import UserPermissions
from src.main import app
from src.pic.application.use_cases.get_acordo_resultados import (
    GetAcordoResultadosUseCase,
)
from src.pic.domain.models.acordo_resultados import (
    AcordoResultados,
    DistribuicaoPublico,
    StatusResumo,
)
from src.pic.domain.models.dashboard import (
    DistribuicaoMotivoSaida,
    ProtocoloIndicador,
    ResultadoProgramaPoint,
)
from src.pic.presentation.di import get_acordo_resultados_use_case

FAKE_ACORDO = AcordoResultados(
    total_participantes=14,
    ativos=StatusResumo(
        total=10, regulares=8, irregulares=2,
        percentual_regular=80.0, percentual_irregular=20.0,
    ),
    inativos=StatusResumo(
        total=4, regulares=3, irregulares=1,
        percentual_regular=75.0, percentual_irregular=25.0,
    ),
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
    evolucao_mensal=[
        ResultadoProgramaPoint(
            mes="2025-01",
            mes_label="Jan/25",
            todos=71.4,
            saude=80.0,
            educacao=60.0,
            assistencia=100.0,
        )
    ],
    motivos_saida=[DistribuicaoMotivoSaida(motivo="Não informado", total=3)],
    distribuicao_raca=[DistribuicaoPublico(categoria="branca", total=6)],
    distribuicao_grupo=[DistribuicaoPublico(categoria="Criança", total=5)],
    distribuicao_ra=[
        DistribuicaoPublico(categoria="Madureira", total=7),
        DistribuicaoPublico(categoria="Centro", total=3),
    ],
    distribuicao_cartao_pic=[
        DistribuicaoPublico(categoria="Retirado", total=5),
        DistribuicaoPublico(categoria="Não retirado", total=4),
        DistribuicaoPublico(categoria="Sem direito", total=3),
    ],
    distribuicao_bolsa_familia=[
        DistribuicaoPublico(categoria="Sim", total=6),
        DistribuicaoPublico(categoria="Não", total=4),
        DistribuicaoPublico(categoria="Não informado", total=2),
    ],
    meta_regularidade=30.5,
)

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


def _make_fake_use_case() -> GetAcordoResultadosUseCase:
    fake_repo = MagicMock()
    fake_repo.get_acordo_resultados = AsyncMock(return_value=FAKE_ACORDO)
    return GetAcordoResultadosUseCase(repository=fake_repo)


@pytest.fixture
def override_auth_superadmin():
    app.dependency_overrides[verify_jwt] = lambda: {"preferred_username": "12345678900"}
    app.dependency_overrides[get_current_user_permissions_v2] = lambda: SUPER_ADMIN
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def override_auth_no_access():
    app.dependency_overrides[verify_jwt] = lambda: {"preferred_username": "99999999999"}
    app.dependency_overrides[get_current_user_permissions_v2] = lambda: NO_ACCESS
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def override_use_case():
    fake = _make_fake_use_case()
    app.dependency_overrides[get_acordo_resultados_use_case] = lambda: fake
    yield fake
    if get_acordo_resultados_use_case in app.dependency_overrides:
        del app.dependency_overrides[get_acordo_resultados_use_case]


@pytest.fixture
async def client(override_auth_superadmin, override_use_case):
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


@pytest.mark.asyncio
async def test_get_acordo_resultados_200_superadmin(client):
    response = await client.get("/api/v2/acordo-resultados")

    assert response.status_code == 200
    body = response.json()
    assert body["can_view_acordo"] is True
    assert body["data"]["total_participantes"] == 14
    assert body["data"]["ativos"]["regulares"] == 8
    assert body["data"]["inativos"]["regulares"] == 3


@pytest.mark.asyncio
async def test_response_contains_all_sections(client):
    response = await client.get("/api/v2/acordo-resultados")
    assert response.status_code == 200
    data = response.json()["data"]

    assert "total_participantes" in data
    assert "ativos" in data
    assert "inativos" in data
    assert "protocolos" in data
    assert "evolucao_mensal" in data
    assert "motivos_saida" in data
    assert "distribuicao_raca" in data
    assert "distribuicao_grupo" in data
    assert "distribuicao_ra" in data
    assert "distribuicao_cartao_pic" in data
    assert "distribuicao_bolsa_familia" in data
    assert data["meta_regularidade"] == 30.5


@pytest.mark.asyncio
async def test_get_acordo_resultados_401_without_auth():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v2/acordo-resultados")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_acordo_resultados_no_access(override_auth_no_access):
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": "Bearer fake-jwt-token"},
    ) as ac:
        response = await ac.get("/api/v2/acordo-resultados")

    assert response.status_code == 200
    body = response.json()
    assert body["can_view_acordo"] is False
    assert body["data"]["total_participantes"] == 0


@pytest.mark.asyncio
async def test_bypass_cache_query_param_accepted(client):
    response = await client.get("/api/v2/acordo-resultados?bypass_cache=true")
    assert response.status_code == 200
