import pytest
from httpx import ASGITransport, AsyncClient

from src.core.security.jwt import get_current_user_permissions, verify_jwt
from src.core.security.permissions_models import UserPermissions
from src.main import app


@pytest.fixture
def override_auth():
    token_payload = {"preferred_username": "12345678900"}
    app.dependency_overrides[verify_jwt] = lambda: token_payload
    app.dependency_overrides[get_current_user_permissions] = lambda: UserPermissions(
        cpf="12345678900",
        is_admin=True,
        is_super_admin=True,
        secretaria_acesso="TODOS",
    )
    yield
    app.dependency_overrides.clear()


@pytest.fixture
async def client(override_auth):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_get_dashboard_200(client, override_auth):
    response = await client.get("/api/v2/dashboard")

    assert response.status_code == 200
    body = response.json()
    assert body["can_view_dashboard"] is not None
    assert "data" in body
    data = body["data"]
    assert "total_participantes" in data
    assert "total_regulares" in data
    assert "total_irregulares" in data
    assert "protocolos" in data
    assert "filters" not in body


@pytest.mark.asyncio
async def test_get_dashboard_401_without_auth():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client_no_auth:
        response = await client_no_auth.get("/api/v2/dashboard")
        assert response.status_code == 401
