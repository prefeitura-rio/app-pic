"""E2E tests for the geospatial V2 endpoints.

Tests the HTTP layer — routing, auth, request parsing, response schema — using
the same ASGI test client pattern as the other v2 e2e tests.  The use cases are
faked so no PostgREST or Redis are involved.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from src.core.security.jwt import get_current_user_permissions_v2, verify_jwt
from src.core.security.permissions_models import UserPermissions
from src.main import app
from src.pic.domain.models.filters import FilterOption
from src.pic.domain.models.geospatial import GeospatialLayer
from src.pic.presentation.di import (
    get_geospatial_filter_options_use_case,
    get_geospatial_filter_vocabulary_use_case,
    get_geospatial_layers_use_case,
)

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeLayersUseCase:
    def __init__(self, layers: list[GeospatialLayer] | None = None, error: Exception | None = None):
        self.layers = layers or [
            GeospatialLayer(
                tipo_camada="BAIRRO",
                tipo_geometria="poligono",
                categoria="BAIRRO",
                id="1",
                id_unico="1-CENTRO",
                nome="CENTRO",
                geometry_geojson='{"type":"Polygon","coordinates":[]}',
            )
        ]
        self.error = error
        self.received_filters = {}

    async def execute(self, filters, user_token=None, bypass_cache=False):
        self.received_filters = filters.model_dump(exclude_none=True)
        self.received_user_token = user_token
        if self.error:
            raise self.error

        class Output:
            pass

        out = Output()
        out.data = self.layers
        return out


class FakeFilterOptionsUseCase:
    def __init__(
        self,
        options: list[FilterOption] | None = None,
        error: Exception | None = None,
    ):
        self.options = options or [FilterOption(id="BAIRRO", label="BAIRRO")]
        self.error = error
        self.received: dict = {}

    async def execute(
        self, field, filters=None, user_token=None, bypass_cache=False
    ):
        self.received = {
            "field": field,
            "filters": filters.model_dump(exclude_none=True)
            if filters is not None
            else {},
            "user_token": user_token,
        }
        if self.error:
            raise self.error
        return self.options


class FakeVocabularyUseCase:
    async def execute(self, user_token=None, bypass_cache=False):
        from src.pic.domain.models.geospatial import GeospatialFilterOptions

        return GeospatialFilterOptions(
            tipos_camada=[FilterOption(id="BAIRRO", label="BAIRRO")]
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
def layers_use_case():
    return FakeLayersUseCase()


@pytest.fixture
def filter_options_use_case():
    return FakeFilterOptionsUseCase()


@pytest.fixture
def vocabulary_use_case():
    return FakeVocabularyUseCase()


@pytest.fixture
def override_use_cases(layers_use_case, filter_options_use_case, vocabulary_use_case):
    app.dependency_overrides[get_geospatial_layers_use_case] = lambda: layers_use_case
    app.dependency_overrides[get_geospatial_filter_options_use_case] = (
        lambda: filter_options_use_case
    )
    app.dependency_overrides[get_geospatial_filter_vocabulary_use_case] = (
        lambda: vocabulary_use_case
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
# Tests: GET /api/v2/geospatial/layers
# ---------------------------------------------------------------------------


class TestGetGeospatialLayers:
    @pytest.mark.asyncio
    async def test_returns_200_with_data(self, client):
        resp = await client.get("/api/v2/geospatial/layers")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert len(body["data"]) == 1
        assert body["data"][0]["tipo_camada"] == "BAIRRO"

    @pytest.mark.asyncio
    async def test_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/api/v2/geospatial/layers")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_filter_forwarded_to_use_case(
        self, client, layers_use_case
    ):
        await client.get("/api/v2/geospatial/layers?tipo_camada=BAIRRO")
        assert layers_use_case.received_filters.get("tipo_camada") == "BAIRRO"

    @pytest.mark.asyncio
    async def test_x_access_token_wins_over_id_token(
        self, client, layers_use_case
    ):
        """The access token (X-Access-Token) wins over the id token for the
        data-proxy call (same semantic as participants)."""
        await client.get("/api/v2/geospatial/layers")
        assert layers_use_case.received_user_token == "fake-access-token"

    @pytest.mark.asyncio
    async def test_500_on_use_case_error(
        self, override_auth, override_use_cases
    ):
        app.dependency_overrides[get_geospatial_layers_use_case] = lambda: FakeLayersUseCase(
            error=RuntimeError("boom")
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Authorization": "Bearer fake-jwt-token"},
        ) as c:
            resp = await c.get("/api/v2/geospatial/layers")
        assert resp.status_code == 500
        app.dependency_overrides.pop(get_geospatial_layers_use_case, None)


# ---------------------------------------------------------------------------
# Tests: GET /api/v2/geospatial/filter-options
# ---------------------------------------------------------------------------


class TestGetGeospatialFilterOptions:
    @pytest.mark.asyncio
    async def test_returns_200_with_field_and_options(self, client):
        resp = await client.get("/api/v2/geospatial/filter-options?field=tipos_camada")
        assert resp.status_code == 200
        body = resp.json()
        assert body["field"] == "tipos_camada"
        assert len(body["options"]) == 1
        assert body["options"][0]["id"] == "BAIRRO"

    @pytest.mark.asyncio
    async def test_field_param_forwarded_to_use_case(
        self, client, filter_options_use_case
    ):
        await client.get("/api/v2/geospatial/filter-options?field=categorias")
        assert filter_options_use_case.received["field"] == "categorias"

    @pytest.mark.asyncio
    async def test_missing_field_param_returns_422(self, client):
        resp = await client.get("/api/v2/geospatial/filter-options")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_active_filters_forwarded(self, client, filter_options_use_case):
        await client.get(
            "/api/v2/geospatial/filter-options?field=bairros&tipo_camada=BAIRRO"
        )
        filters = filter_options_use_case.received.get("filters", {})
        assert filters.get("tipo_camada") == "BAIRRO"

    @pytest.mark.asyncio
    async def test_500_on_use_case_error(self, override_auth, override_use_cases):
        app.dependency_overrides[get_geospatial_filter_options_use_case] = (
            lambda: FakeFilterOptionsUseCase(error=RuntimeError("oops"))
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Authorization": "Bearer fake-jwt-token"},
        ) as c:
            resp = await c.get("/api/v2/geospatial/filter-options?field=tipos_camada")
        assert resp.status_code == 500
        app.dependency_overrides.pop(get_geospatial_filter_options_use_case, None)


# ---------------------------------------------------------------------------
# Tests: GET /api/v2/geospatial/filters (deprecated bulk)
# ---------------------------------------------------------------------------


class TestGetGeospatialFilters:
    @pytest.mark.asyncio
    async def test_returns_200_with_vocabulary(self, client):
        resp = await client.get("/api/v2/geospatial/filters")
        assert resp.status_code == 200
        body = resp.json()
        assert "tipos_camada" in body
        assert len(body["tipos_camada"]) == 1
