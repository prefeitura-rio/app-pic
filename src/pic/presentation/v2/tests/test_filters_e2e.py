import pytest
from httpx import ASGITransport, AsyncClient

from src.core.security.jwt import get_current_user_permissions_v2, verify_jwt
from src.core.security.permissions_models import UserPermissions
from src.main import app
from src.pic.domain.models.filters import FilterOption
from src.pic.infrastructure.postgrest_client.errors import PostgrestError
from src.pic.presentation.di import (
    get_admin_repo,
    get_filter_options_use_case,
)


class FakeOptionsUseCase:
    def __init__(
        self, error: Exception | None = None, events: list[str] | None = None
    ):
        self.error = error
        self.events = events if events is not None else []
        self.received: dict = {}

    async def execute(
        self,
        field,
        filters,
        permissions=None,
        user_token=None,
        bypass_cache=False,
    ):
        self.received = {
            "field": field,
            "filters": filters,
            "user_token": user_token,
            "bypass_cache": bypass_cache,
        }
        self.events.append("options_use_case")
        if self.error:
            raise self.error
        return [FilterOption(id="Centro", label="Centro")]


class FakeAdminRepo:
    def __init__(self, events: list[str] | None = None):
        self.events = events if events is not None else []
        self.self_heal_cpfs: list[str] = []

    async def self_heal_policy_sync(self, cpf: str) -> None:
        self.self_heal_cpfs.append(cpf)
        self.events.append("self_heal")


@pytest.fixture
def override_auth():
    token_payload = {"preferred_username": "12345678900"}
    app.dependency_overrides[verify_jwt] = lambda: token_payload
    app.dependency_overrides[get_current_user_permissions_v2] = lambda: UserPermissions(
        cpf="12345678900",
        is_admin=True,
        is_super_admin=True,
        secretarias_acesso=["SME", "SMS", "SMAS"],
    )
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def override_use_cases():
    events: list[str] = []
    options_use_case = FakeOptionsUseCase(events=events)
    admin_repo = FakeAdminRepo(events=events)
    app.dependency_overrides[get_filter_options_use_case] = lambda: options_use_case
    app.dependency_overrides[get_admin_repo] = lambda: admin_repo
    yield options_use_case, admin_repo
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


@pytest.mark.asyncio
async def test_filters_returns_field_options_envelope(client, override_use_cases):
    response = await client.get(
        "/api/v2/filters", params={"field": "bairros", "status": "Ativo"}
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"field", "options"}
    assert body["field"] == "bairros"
    assert body["options"] == [{"id": "Centro", "label": "Centro"}]

    options_use_case, _ = override_use_cases
    assert options_use_case.received["field"] == "bairros"
    assert options_use_case.received["user_token"] == "fake-access-token"
    assert options_use_case.received["filters"].status == "Ativo"


@pytest.mark.asyncio
async def test_filters_missing_field_is_422(client):
    response = await client.get("/api/v2/filters")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_filters_unknown_field_is_422(client):
    response = await client.get("/api/v2/filters", params={"field": "nao_existe"})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_filters_falls_back_to_id_token_without_access_token_header(
    override_auth, override_use_cases
):
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": "Bearer fake-jwt-token"},
    ) as ac:
        response = await ac.get("/api/v2/filters", params={"field": "bairros"})

    assert response.status_code == 200
    options_use_case, _ = override_use_cases
    assert options_use_case.received["user_token"] == "fake-jwt-token"


@pytest.mark.asyncio
async def test_policy_self_heal_runs_before_filters_read(client, override_use_cases):
    response = await client.get("/api/v2/filters", params={"field": "bairros"})

    assert response.status_code == 200
    _, admin_repo = override_use_cases
    assert admin_repo.self_heal_cpfs == ["12345678900"]
    assert admin_repo.events == ["self_heal", "options_use_case"]


@pytest.mark.asyncio
async def test_filters_maps_postgrest_error_to_502(override_auth):
    app.dependency_overrides[get_filter_options_use_case] = lambda: (
        FakeOptionsUseCase(error=PostgrestError("data-proxy down"))
    )
    app.dependency_overrides[get_admin_repo] = lambda: FakeAdminRepo()
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": "Bearer fake-jwt-token"},
    ) as ac:
        response = await ac.get("/api/v2/filters", params={"field": "bairros"})

    assert response.status_code == 502
    assert response.json()["detail"] == "data-proxy down"


@pytest.mark.asyncio
async def test_filters_require_authentication(override_use_cases):
    app.dependency_overrides[verify_jwt] = lambda: {"preferred_username": "x"}
    app.dependency_overrides[get_current_user_permissions_v2] = lambda: UserPermissions(
        cpf="x"
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v2/filters", params={"field": "bairros"})

    assert response.status_code == 401
