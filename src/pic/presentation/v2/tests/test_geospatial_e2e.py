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
    get_detalhes_regiao_use_case,
    get_geospatial_filter_options_use_case,
    get_geospatial_filter_vocabulary_use_case,
    get_geospatial_layers_use_case,
    get_protocolos_use_case,
    get_regularidade_por_camada_use_case,
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


class FakeRegularidadeUseCase:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.received: dict = {}

    async def execute(
        self,
        camada,
        user_token=None,
        user_id=None,
        bypass_cache=False,
        status=None,
        cohortes=None,
        protocolo_id=None,
    ):
        self.received = {
            "camada": camada,
            "user_token": user_token,
            "user_id": user_id,
            "bypass_cache": bypass_cache,
            "status": status,
            "cohortes": cohortes,
            "protocolo_id": protocolo_id,
        }
        if self.error:
            raise self.error

        class Output:
            pass

        out = Output()
        out.features = [
            {
                "type": "Feature",
                "properties": {
                    "id": "1",
                    "nome": "Rio Comprido",
                    "total_participantes": 150,
                    "total_regulares": 100,
                    "total_irregulares": 50,
                    "taxa_regularidade": 66.7,
                },
                "geometry": {"type": "Polygon", "coordinates": []},
            }
        ]
        out.meta = {
            "camada": camada,
            "total_regioes": 1,
            "regioes_com_dados": 1,
            "regioes_sem_dados": 0,
            "agregados_sem_geometria": [],
        }
        return out


class FakeProtocolosUseCase:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.received: dict = {}

    async def execute(self, user_token=None, user_id=None, bypass_cache=False):
        self.received = {
            "user_token": user_token,
            "user_id": user_id,
            "bypass_cache": bypass_cache,
        }
        if self.error:
            raise self.error

        from src.pic.domain.models.geospatial import ProtocoloOption

        return [
            ProtocoloOption(
                protocolo_id="sms_vacinacao_pentavalente",
                protocolo_secretaria="SMS",
                protocolo_descricao="Criança com 3ª dose da vacina pentavalente no 1 ano",
            )
        ]


class FakeDetalhesRegiaoUseCase:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.received: dict = {}

    async def execute(
        self,
        camada,
        regiao,
        user_token=None,
        user_id=None,
        bypass_cache=False,
        status=None,
        cohortes=None,
        protocolo_id=None,
    ):
        self.received = {
            "camada": camada,
            "regiao": regiao,
            "user_token": user_token,
            "user_id": user_id,
            "bypass_cache": bypass_cache,
            "status": status,
            "cohortes": cohortes,
            "protocolo_id": protocolo_id,
        }
        if self.error:
            raise self.error

        from src.pic.domain.models.geospatial import (
            RegiaoDetalhes,
            RegiaoProtocoloAggregate,
            RegiaoRegularidadeResumo,
        )

        return RegiaoDetalhes(
            camada=camada,
            regiao=regiao,
            geral=RegiaoRegularidadeResumo(
                total_participantes=150,
                total_regulares=100,
                total_irregulares=50,
                taxa_regularidade=66.7,
            ),
            protocolo_geral=(
                RegiaoRegularidadeResumo(
                    total_participantes=1000,
                    total_regulares=996,
                    total_irregulares=4,
                    taxa_regularidade=99.6,
                )
                if protocolo_id
                else None
            ),
            protocolos=[
                RegiaoProtocoloAggregate(
                    protocolo_id="sms_vacinacao_pentavalente",
                    protocolo_secretaria="SMS",
                    protocolo_descricao="Vacinação pentavalente",
                    total_participantes=80,
                    total_regulares=60,
                    total_irregulares=20,
                    taxa_regularidade=75.0,
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
def layers_use_case():
    return FakeLayersUseCase()


@pytest.fixture
def filter_options_use_case():
    return FakeFilterOptionsUseCase()


@pytest.fixture
def vocabulary_use_case():
    return FakeVocabularyUseCase()


@pytest.fixture
def regularidade_use_case():
    return FakeRegularidadeUseCase()


@pytest.fixture
def protocolos_use_case():
    return FakeProtocolosUseCase()


@pytest.fixture
def detalhes_regiao_use_case():
    return FakeDetalhesRegiaoUseCase()


@pytest.fixture
def override_use_cases(layers_use_case, filter_options_use_case, vocabulary_use_case, regularidade_use_case, protocolos_use_case, detalhes_regiao_use_case):
    app.dependency_overrides[get_geospatial_layers_use_case] = lambda: layers_use_case
    app.dependency_overrides[get_geospatial_filter_options_use_case] = (
        lambda: filter_options_use_case
    )
    app.dependency_overrides[get_geospatial_filter_vocabulary_use_case] = (
        lambda: vocabulary_use_case
    )
    app.dependency_overrides[get_regularidade_por_camada_use_case] = (
        lambda: regularidade_use_case
    )
    app.dependency_overrides[get_protocolos_use_case] = lambda: protocolos_use_case
    app.dependency_overrides[get_detalhes_regiao_use_case] = (
        lambda: detalhes_regiao_use_case
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


# ---------------------------------------------------------------------------
# Tests: GET /api/v2/geospatial/regularidade
# ---------------------------------------------------------------------------


class TestGetRegularidadePorCamada:
    @pytest.mark.asyncio
    async def test_returns_200_with_bairro_features(self, client):
        resp = await client.get("/api/v2/geospatial/regularidade?camada=bairro")
        assert resp.status_code == 200
        body = resp.json()
        assert body["type"] == "FeatureCollection"
        assert len(body["features"]) == 1
        assert body["features"][0]["properties"]["nome"] == "Rio Comprido"
        assert body["features"][0]["properties"]["taxa_regularidade"] == 66.7
        assert body["meta"]["camada"] == "bairro"

    @pytest.mark.asyncio
    async def test_ra_camada_accepted(self, client, regularidade_use_case):
        resp = await client.get("/api/v2/geospatial/regularidade?camada=ra")
        assert resp.status_code == 200
        assert regularidade_use_case.received["camada"] == "ra"

    @pytest.mark.asyncio
    async def test_camadas_estaticas_accepted(self, client):
        for camada in ("cas", "cre", "ap"):
            resp = await client.get(
                f"/api/v2/geospatial/regularidade?camada={camada}"
            )
            assert resp.status_code == 200, camada
            assert resp.json()["meta"]["camada"] == camada

    @pytest.mark.asyncio
    async def test_missing_camada_param_returns_422(self, client):
        resp = await client.get("/api/v2/geospatial/regularidade")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_camada_returns_422(self, client):
        resp = await client.get("/api/v2/geospatial/regularidade?camada=subprefeitura")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_bypass_cache_forwarded(self, client, regularidade_use_case):
        await client.get(
            "/api/v2/geospatial/regularidade?camada=bairro&bypass_cache=true"
        )
        assert regularidade_use_case.received["bypass_cache"] is True

    @pytest.mark.asyncio
    async def test_status_multiselect_forwarded(self, client, regularidade_use_case):
        await client.get("/api/v2/geospatial/regularidade?camada=bairro&status=Ativo")
        assert regularidade_use_case.received["status"] == ["Ativo"]
        await client.get(
            "/api/v2/geospatial/regularidade?camada=bairro"
            "&status=Ativo&status=Inativo"
        )
        assert regularidade_use_case.received["status"] == ["Ativo", "Inativo"]

    @pytest.mark.asyncio
    async def test_invalid_status_returns_422(self, client):
        resp = await client.get(
            "/api/v2/geospatial/regularidade?camada=bairro&status=Banana"
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_cohortes_multiselect_forwarded(self, client, regularidade_use_case):
        await client.get(
            "/api/v2/geospatial/regularidade"
            "?camada=bairro&cohortes=2025-03-01&cohortes=2026-07-01"
        )
        assert regularidade_use_case.received["cohortes"] == [
            "2025-03-01",
            "2026-07-01",
        ]

    @pytest.mark.asyncio
    async def test_invalid_cohort_date_returns_422(self, client):
        resp = await client.get(
            "/api/v2/geospatial/regularidade?camada=bairro&cohortes=2025-13-99"
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_protocolo_id_forwarded(self, client, regularidade_use_case):
        await client.get(
            "/api/v2/geospatial/regularidade?camada=bairro"
            "&protocolo_id=sms_vacinacao_pentavalente"
        )
        assert (
            regularidade_use_case.received["protocolo_id"]
            == "sms_vacinacao_pentavalente"
        )

    @pytest.mark.asyncio
    async def test_x_access_token_wins_over_id_token(
        self, client, regularidade_use_case
    ):
        await client.get("/api/v2/geospatial/regularidade?camada=bairro")
        assert regularidade_use_case.received["user_token"] == "fake-access-token"

    @pytest.mark.asyncio
    async def test_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/api/v2/geospatial/regularidade?camada=bairro")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_deprecated_bairros_regularidade_alias_still_works(
        self, client, regularidade_use_case
    ):
        resp = await client.get("/api/v2/geospatial/bairros-regularidade")
        assert resp.status_code == 200
        assert regularidade_use_case.received["camada"] == "bairro"


# ---------------------------------------------------------------------------
# Tests: GET /api/v2/geospatial/protocolos
# ---------------------------------------------------------------------------


class TestGetProtocolos:
    @pytest.mark.asyncio
    async def test_returns_200_with_protocolos(self, client):
        resp = await client.get("/api/v2/geospatial/protocolos")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["protocolos"]) == 1
        proto = body["protocolos"][0]
        assert proto["protocolo_id"] == "sms_vacinacao_pentavalente"
        assert proto["protocolo_secretaria"] == "SMS"

    @pytest.mark.asyncio
    async def test_x_access_token_wins_over_id_token(
        self, client, protocolos_use_case
    ):
        await client.get("/api/v2/geospatial/protocolos")
        assert protocolos_use_case.received["user_token"] == "fake-access-token"

    @pytest.mark.asyncio
    async def test_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/api/v2/geospatial/protocolos")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Tests: GET /api/v2/geospatial/regiao/detalhes (fase 3j)
# ---------------------------------------------------------------------------


class TestGetRegiaoDetalhes:
    @pytest.mark.asyncio
    async def test_returns_200_with_geral_e_protocolos(self, client):
        resp = await client.get(
            "/api/v2/geospatial/regiao/detalhes?camada=bairro&regiao=Centro"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["camada"] == "bairro"
        assert body["regiao"] == "Centro"
        assert body["geral"]["total_participantes"] == 150
        assert body["geral"]["taxa_regularidade"] == 66.7
        assert len(body["protocolos"]) == 1
        proto = body["protocolos"][0]
        assert proto["protocolo_id"] == "sms_vacinacao_pentavalente"
        assert proto["protocolo_secretaria"] == "SMS"
        assert proto["total_irregulares"] == 20
        assert proto["taxa_regularidade"] == 75.0

    @pytest.mark.asyncio
    async def test_regiao_forwarded_to_use_case(self, client, detalhes_regiao_use_case):
        await client.get(
            "/api/v2/geospatial/regiao/detalhes?camada=ra&regiao=Rio%20Comprido"
        )
        assert detalhes_regiao_use_case.received["camada"] == "ra"
        assert detalhes_regiao_use_case.received["regiao"] == "Rio Comprido"

    @pytest.mark.asyncio
    async def test_missing_params_return_422(self, client):
        resp = await client.get("/api/v2/geospatial/regiao/detalhes")
        assert resp.status_code == 422
        resp = await client.get(
            "/api/v2/geospatial/regiao/detalhes?camada=bairro"
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_camada_returns_422(self, client):
        resp = await client.get(
            "/api/v2/geospatial/regiao/detalhes?camada=subprefeitura&regiao=X"
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_filters_multiselect_forwarded(
        self, client, detalhes_regiao_use_case
    ):
        await client.get(
            "/api/v2/geospatial/regiao/detalhes?camada=bairro&regiao=Centro"
            "&status=Ativo&status=Inativo&cohortes=2025-03-01&cohortes=2026-07-01"
        )
        assert detalhes_regiao_use_case.received["status"] == ["Ativo", "Inativo"]
        assert detalhes_regiao_use_case.received["cohortes"] == [
            "2025-03-01",
            "2026-07-01",
        ]

    @pytest.mark.asyncio
    async def test_invalid_status_returns_422(self, client):
        resp = await client.get(
            "/api/v2/geospatial/regiao/detalhes?camada=bairro"
            "&regiao=Centro&status=Banana"
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_cohort_date_returns_422(self, client):
        resp = await client.get(
            "/api/v2/geospatial/regiao/detalhes?camada=bairro"
            "&regiao=Centro&cohortes=2025-13-99"
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_bypass_cache_forwarded(self, client, detalhes_regiao_use_case):
        await client.get(
            "/api/v2/geospatial/regiao/detalhes?camada=bairro"
            "&regiao=Centro&bypass_cache=true"
        )
        assert detalhes_regiao_use_case.received["bypass_cache"] is True

    @pytest.mark.asyncio
    async def test_x_access_token_wins_over_id_token(
        self, client, detalhes_regiao_use_case
    ):
        await client.get(
            "/api/v2/geospatial/regiao/detalhes?camada=bairro&regiao=Centro"
        )
        assert detalhes_regiao_use_case.received["user_token"] == "fake-access-token"

    @pytest.mark.asyncio
    async def test_protocolo_id_forwarded_e_protocolo_geral_na_resposta(
        self, client, detalhes_regiao_use_case
    ):
        resp = await client.get(
            "/api/v2/geospatial/regiao/detalhes?camada=bairro&regiao=Centro"
            "&protocolo_id=smas_acesso_alimentacao"
        )
        assert resp.status_code == 200
        assert (
            detalhes_regiao_use_case.received["protocolo_id"]
            == "smas_acesso_alimentacao"
        )
        body = resp.json()
        assert body["protocolo_geral"] is not None
        assert body["protocolo_geral"]["taxa_regularidade"] == 99.6
        assert body["protocolo_geral"]["total_irregulares"] == 4

    @pytest.mark.asyncio
    async def test_sem_protocolo_id_protocolo_geral_null(self, client):
        resp = await client.get(
            "/api/v2/geospatial/regiao/detalhes?camada=bairro&regiao=Centro"
        )
        assert resp.status_code == 200
        assert resp.json()["protocolo_geral"] is None

    @pytest.mark.asyncio
    async def test_500_on_use_case_error(self, override_auth, override_use_cases):
        app.dependency_overrides[get_detalhes_regiao_use_case] = (
            lambda: FakeDetalhesRegiaoUseCase(error=RuntimeError("boom"))
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Authorization": "Bearer fake-jwt-token"},
        ) as c:
            resp = await c.get(
                "/api/v2/geospatial/regiao/detalhes?camada=bairro&regiao=Centro"
            )
        assert resp.status_code == 500
        app.dependency_overrides.pop(get_detalhes_regiao_use_case, None)

    @pytest.mark.asyncio
    async def test_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get(
                "/api/v2/geospatial/regiao/detalhes?camada=bairro&regiao=Centro"
            )
        assert resp.status_code in (401, 403)
