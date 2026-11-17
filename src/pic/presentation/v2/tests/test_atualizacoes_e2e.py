"""E2E tests for the atualizações V2 endpoint (Painel de Atualizações).

Mesmo padrão do test_monitoring_e2e.py: ASGI test client, use case fake
(sem PostgREST/Redis), autenticação sobrescrita. Cobre roteamento, parsing
de query params, repasse do token e mapeamento de erros.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from src.core.security.jwt import get_current_user_permissions_v2, verify_jwt
from src.core.security.permissions_models import UserPermissions
from src.main import app
from src.pic.domain.models.atualizacoes import (
    AtualizacoesMeta,
    AtualizacoesRegionaisResponse,
)
from src.pic.infrastructure.postgrest_client.errors import PostgrestError
from src.pic.presentation.di import get_atualizacoes_regionais_use_case


class FakeAtualizacoesUseCase:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.received: dict = {}

    async def execute(
        self,
        camada,
        regiao,
        permissions=None,
        user_token=None,
        user_id=None,
        semana=None,
        semanas_comparacao=4,
        bypass_cache=False,
    ):
        self.received = {
            "camada": camada,
            "regiao": regiao,
            "user_token": user_token,
            "user_id": user_id,
            "semana": semana,
            "semanas_comparacao": semanas_comparacao,
            "bypass_cache": bypass_cache,
        }
        if self.error:
            raise self.error
        # Mesma validação XOR do use case real (a rota mapeia ValueError→422)
        if (camada is None) != (regiao is None):
            raise ValueError("camada e regiao devem ser passadas juntas (ou ambas omitidas)")
        return AtualizacoesRegionaisResponse(
            can_view_atualizacoes=True,
            meta=AtualizacoesMeta(semana_referencia="2026-11-02", tem_comparativo=True),
        )


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
def use_case():
    return FakeAtualizacoesUseCase()


@pytest.fixture
def override_use_cases(use_case):
    app.dependency_overrides[get_atualizacoes_regionais_use_case] = lambda: use_case
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
# Tests: GET /api/v2/dashboard/atualizacoes-regionais
# ---------------------------------------------------------------------------


class TestGetAtualizacoesRegionais:
    @pytest.mark.asyncio
    async def test_returns_200(self, client):
        resp = await client.get(
            "/api/v2/dashboard/atualizacoes-regionais?camada=cas&regiao=2ª%20CAS"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["can_view_atualizacoes"] is True
        assert body["meta"]["semana_referencia"] == "2026-11-02"
        assert body["meta"]["tem_comparativo"] is True
        assert body["data"] is None

    @pytest.mark.asyncio
    async def test_sem_regionais_segue_escopo_do_usuario(self, client, use_case):
        """Sem camada/região → painel do escopo do usuário (RLS)."""
        resp = await client.get("/api/v2/dashboard/atualizacoes-regionais")
        assert resp.status_code == 200
        assert use_case.received["camada"] is None
        assert use_case.received["regiao"] is None

    @pytest.mark.asyncio
    async def test_camada_sem_regiao_422(self, client):
        resp = await client.get(
            "/api/v2/dashboard/atualizacoes-regionais?camada=cas"
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_params_forwarded(self, client, use_case):
        await client.get(
            "/api/v2/dashboard/atualizacoes-regionais?camada=cas&regiao=2ª%20CAS"
            "&semana=2026-11-02&bypass_cache=true"
        )
        assert use_case.received["camada"] == "cas"
        assert use_case.received["regiao"] == "2ª CAS"
        assert use_case.received["semana"] == "2026-11-02"
        assert use_case.received["bypass_cache"] is True

    @pytest.mark.asyncio
    async def test_semanas_comparacao_default_4(self, client, use_case):
        await client.get("/api/v2/dashboard/atualizacoes-regionais")
        assert use_case.received["semanas_comparacao"] == 4

    @pytest.mark.asyncio
    async def test_semanas_comparacao_forwarded(self, client, use_case):
        await client.get(
            "/api/v2/dashboard/atualizacoes-regionais?semanas_comparacao=1"
        )
        assert use_case.received["semanas_comparacao"] == 1

    @pytest.mark.asyncio
    async def test_semanas_comparacao_invalida_422(self, client):
        for valor in ("0", "3", "5", "abc"):
            resp = await client.get(
                f"/api/v2/dashboard/atualizacoes-regionais?semanas_comparacao={valor}"
            )
            assert resp.status_code == 422, f"valor {valor!r} deveria dar 422"

    @pytest.mark.asyncio
    async def test_user_id_forwarded(self, client, use_case):
        await client.get(
            "/api/v2/dashboard/atualizacoes-regionais?camada=cas&regiao=2ª%20CAS"
        )
        assert use_case.received["user_id"] == "00000000000"

    @pytest.mark.asyncio
    async def test_x_access_token_forwarded(self, client, use_case):
        await client.get(
            "/api/v2/dashboard/atualizacoes-regionais?camada=cas&regiao=2ª%20CAS"
        )
        assert use_case.received["user_token"] == "fake-access-token"

    @pytest.mark.asyncio
    async def test_maps_postgrest_error_to_502(self, override_auth):
        app.dependency_overrides[get_atualizacoes_regionais_use_case] = (
            lambda: FakeAtualizacoesUseCase(error=PostgrestError("boom", code="P0001"))
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Authorization": "Bearer fake-jwt-token"},
        ) as ac:
            resp = await ac.get(
                "/api/v2/dashboard/atualizacoes-regionais?camada=cas&regiao=2ª%20CAS"
            )
        assert resp.status_code == 502
        assert resp.json()["detail"] == "boom"

    @pytest.mark.asyncio
    async def test_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                "/api/v2/dashboard/atualizacoes-regionais?camada=cas&regiao=2ª%20CAS"
            )
        assert resp.status_code in (401, 403)
