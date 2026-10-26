"""Unit tests for PostgrestGeospatialRepository.

Uses the same FakeDataProxy / httpx.MockTransport pattern as the participant
and dashboard repository tests — no real network or Redis involved.

Coverage:
    - fetch_layers: rolling-window concurrent fetch (Prefer: count=exact)
    - fetch_layers: single page (≤ PAGE_SIZE rows)
    - fetch_layers: multi-page with rolling window (2 at a time)
    - fetch_layers: cache hit / miss / bypass
    - get_filter_options: per-field lazy vocab
    - get_filter_options: unknown field returns []
    - get_filter_options: cache hit / miss
    - get_filter_vocabulary: bulk (backward compat) calls all 7 fields
    - _make_layers_cache_key: deterministic, filter-dependent
    - _make_filter_cache_key: deterministic, field + filter-dependent
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.pic.domain.models.filters import FilterOption
from src.pic.domain.models.geospatial import GeospatialLayer
from src.pic.infrastructure.postgrest_client.client import PostgrestClient
from src.pic.infrastructure.postgrest_client.config import PostgrestClientConfig
from src.pic.infrastructure.repositories.postgrest_geospatial_repository import (
    _TABLE,
    PostgrestGeospatialRepository,
    _make_filter_cache_key,
    _make_layers_cache_key,
)

# ---------------------------------------------------------------------------
# Config & helpers
# ---------------------------------------------------------------------------

CONFIG = PostgrestClientConfig(
    base_url="https://data-proxy.example/",
    schema="app_pequenos_cariocas",
    token_url="https://keycloak.example/token",
    client_id="pic-client",
    client_secret="pic-secret",
)


def _make_layer_row(id: str = "1", tipo_camada: str = "BAIRRO") -> dict:
    return {
        "tipo_camada": tipo_camada,
        "tipo_geometria": "poligono",
        "categoria": "BAIRRO",
        "id": id,
        "id_unico": f"{id}-TEST",
        "nome": f"Layer {id}",
        # PostgREST returns `geometry` as a GeoJSON object (not a string).
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
        },
        "regional": "1.0",
        "bairro": None,
        "regiao_administrativa": None,
        "subprefeitura": None,
        "metadata": None,
    }


# Real row shape from the production endpoint_camadas_geoespaciais table
# (point geometry, string id, JSON-string metadata) — used to assert exact
# parity with the legacy BigQuery ST_AsGeoJSON contract.
REAL_ESCOLA_ROW = {
    "tipo_camada": "ESCOLA",
    "tipo_geometria": "ponto",
    "categoria": "ESCOLA",
    "id": "514012",
    "id_unico": "514012-ESCOLA MUNICIPAL J. CARLOS",
    "nome": "ESCOLA MUNICIPAL J. CARLOS",
    "geometry": {
        "type": "Point",
        "coordinates": [-43.314841, -22.824717],
    },
    "regional": "05ª CRE",
    "bairro": "IRAJÁ",
    "regiao_administrativa": "14ª IRAJA",
    "subprefeitura": "ZONA NORTE III",
    "metadata": '{"cre":"5","designacao":"514012","rua":"RUA RIBATEJO, 245"}',
}


class FakeDataProxy:
    """Minimal fake PostgREST data-proxy.

    Behaviour:
    - Keycloak requests → dummy token response
    - Table requests against _TABLE → returns rows from `pages` list in order,
      respecting ?offset and ?limit query params; sets Content-Range when
      `Prefer: count=exact` is requested.
    - Other tables → empty list
    """

    def __init__(self, all_rows: list[dict]) -> None:
        self.all_rows = all_rows
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
        if table != _TABLE:
            return httpx.Response(200, json=[], request=request)

        params = dict(request.url.params)
        offset = int(params.get("offset", 0))
        limit = int(params.get("limit", len(self.all_rows)))
        page = self.all_rows[offset: offset + limit]

        headers = {}
        prefer = request.headers.get("prefer", "")
        if "count=exact" in prefer:
            total = len(self.all_rows)
            headers["Content-Range"] = f"{offset}-{offset + len(page) - 1}/{total}"

        return httpx.Response(200, json=page, headers=headers, request=request)


def _make_repo(
    all_rows: list[dict],
    redis_client=None,
) -> tuple[PostgrestGeospatialRepository, FakeDataProxy]:
    fake = FakeDataProxy(all_rows)
    client = PostgrestClient(CONFIG, transport=httpx.MockTransport(fake))
    return PostgrestGeospatialRepository(client, redis_client=redis_client), fake


def _make_redis(cached: object | None = None) -> MagicMock:
    redis = MagicMock()
    if cached is None:
        redis.get = AsyncMock(return_value=None)
    else:
        redis.get = AsyncMock(return_value=json.dumps(cached).encode())
    redis.set = AsyncMock()
    return redis


# ---------------------------------------------------------------------------
# Tests: fetch_layers
# ---------------------------------------------------------------------------


class TestFetchLayersSinglePage:
    """Rows fit in one PostgREST page (≤ 1000)."""

    @pytest.mark.asyncio
    async def test_returns_all_rows(self):
        rows = [_make_layer_row(str(i)) for i in range(5)]
        repo, _ = _make_repo(rows)
        result = await repo.fetch_layers(column_filters={})
        assert len(result) == 5
        assert all(isinstance(r, GeospatialLayer) for r in result)

    @pytest.mark.asyncio
    async def test_single_request_when_fits_in_one_page(self):
        rows = [_make_layer_row(str(i)) for i in range(3)]
        repo, fake = _make_repo(rows)
        await repo.fetch_layers(column_filters={})
        # Only the first (count=exact) request is needed
        data_requests = [r for r in fake.requests if r.url.host != "keycloak.example"]
        assert len(data_requests) == 1

    @pytest.mark.asyncio
    async def test_empty_table_returns_empty_list(self):
        repo, _ = _make_repo([])
        result = await repo.fetch_layers(column_filters={})
        assert result == []

    @pytest.mark.asyncio
    async def test_geometry_object_becomes_geojson_string(self):
        """`geometry` comes from PostgREST as a GeoJSON object; the repo
        must expose it as a `geometry_geojson` JSON string (API parity)."""
        rows = [_make_layer_row("1")]
        repo, _ = _make_repo(rows)
        result = await repo.fetch_layers(column_filters={})
        layer = result[0]
        assert layer.geometry_geojson is not None
        geojson = json.loads(layer.geometry_geojson)
        assert geojson["type"] == "Polygon"
        assert not hasattr(layer, "geometry")

    @pytest.mark.asyncio
    async def test_numeric_id_coerced_to_string(self):
        row = _make_layer_row(12345)  # bigint as returned by PostgREST
        repo, _ = _make_repo([row])
        result = await repo.fetch_layers(column_filters={})
        assert result[0].id == "12345"

    @pytest.mark.asyncio
    async def test_null_geometry_kept_null(self):
        row = _make_layer_row("1")
        row["geometry"] = None
        repo, _ = _make_repo([row])
        result = await repo.fetch_layers(column_filters={})
        assert result[0].geometry_geojson is None

    @pytest.mark.asyncio
    async def test_real_escola_row_full_parity(self):
        """Exact production row (Point geometry, string id, JSON metadata)
        must map losslessly to the legacy API contract."""
        repo, _ = _make_repo([REAL_ESCOLA_ROW])
        result = await repo.fetch_layers(column_filters={})
        layer = result[0]

        assert layer.tipo_camada == "ESCOLA"
        assert layer.tipo_geometria == "ponto"
        assert layer.categoria == "ESCOLA"
        assert layer.id == "514012"
        assert layer.id_unico == "514012-ESCOLA MUNICIPAL J. CARLOS"
        assert layer.nome == "ESCOLA MUNICIPAL J. CARLOS"
        assert layer.regional == "05ª CRE"
        assert layer.bairro == "IRAJÁ"
        assert layer.regiao_administrativa == "14ª IRAJA"
        assert layer.subprefeitura == "ZONA NORTE III"
        assert layer.metadata == (
            '{"cre":"5","designacao":"514012","rua":"RUA RIBATEJO, 245"}'
        )
        # geometry → geometry_geojson (string), same as ST_AsGeoJSON
        geojson = json.loads(layer.geometry_geojson or "{}")
        assert geojson["type"] == "Point"
        assert geojson["coordinates"] == [-43.314841, -22.824717]


class TestFetchLayersMultiPage:
    """Rows exceed 1000 → rolling-window concurrent fetch."""

    @pytest.mark.asyncio
    async def test_fetches_all_rows_across_pages(self):
        # 2500 rows → 3 pages (0..999, 1000..1999, 2000..2499)
        rows = [_make_layer_row(str(i)) for i in range(2500)]
        repo, fake = _make_repo(rows)
        result = await repo.fetch_layers(column_filters={})
        assert len(result) == 2500

    @pytest.mark.asyncio
    async def test_correct_number_of_requests(self):
        """2500 rows: 1 first page + 2 remaining pages = 3 total requests."""
        rows = [_make_layer_row(str(i)) for i in range(2500)]
        repo, fake = _make_repo(rows)
        await repo.fetch_layers(column_filters={})
        data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
        assert len(data_reqs) == 3

    @pytest.mark.asyncio
    async def test_first_request_has_count_exact(self):
        """First request must include Prefer: count=exact."""
        rows = [_make_layer_row(str(i)) for i in range(2)]
        repo, fake = _make_repo(rows)
        await repo.fetch_layers(column_filters={})
        first = fake.requests[0]
        assert "count=exact" in first.headers.get("prefer", "")

    @pytest.mark.asyncio
    async def test_rows_order_preserved(self):
        """Result must be in offset order (page 0, page 1, page 2…)."""
        rows = [_make_layer_row(str(i)) for i in range(2500)]
        repo, _ = _make_repo(rows)
        result = await repo.fetch_layers(column_filters={})
        ids = [r.id for r in result]
        assert ids == [str(i) for i in range(2500)]

    @pytest.mark.asyncio
    async def test_exactly_one_page_boundary(self):
        """Exactly 1000 rows → only the first request is made."""
        rows = [_make_layer_row(str(i)) for i in range(1000)]
        repo, fake = _make_repo(rows)
        await repo.fetch_layers(column_filters={})
        data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
        assert len(data_reqs) == 1

    @pytest.mark.asyncio
    async def test_four_pages_rolling_window(self):
        """4000 rows (4 pages): first + 3 remaining.
        Rolling window=2 → 2 round-trips for remaining pages."""
        rows = [_make_layer_row(str(i)) for i in range(4000)]
        repo, fake = _make_repo(rows)
        result = await repo.fetch_layers(column_filters={})
        assert len(result) == 4000
        data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
        # 1 first + 3 remaining (window=2: 2 + 1)
        assert len(data_reqs) == 4


# ---------------------------------------------------------------------------
# Tests: fetch_layers cache
# ---------------------------------------------------------------------------


class TestFetchLayersCache:
    @pytest.mark.asyncio
    async def test_cache_miss_writes_to_redis(self):
        rows = [_make_layer_row("1")]
        redis = _make_redis(None)
        repo, _ = _make_repo(rows, redis_client=redis)
        await repo.fetch_layers(column_filters={})
        redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cache_hit_skips_postgrest(self):
        cached = [_make_layer_row("1")]
        redis = _make_redis(cached)
        repo, fake = _make_repo(cached, redis_client=redis)
        result = await repo.fetch_layers(column_filters={})
        # No PostgREST requests when cache hit
        data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
        assert len(data_reqs) == 0
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_bypass_cache_still_fetches(self):
        cached = [_make_layer_row("1")]
        redis = _make_redis(cached)
        repo, fake = _make_repo(cached, redis_client=redis)
        await repo.fetch_layers(column_filters={}, bypass_cache=True)
        data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
        assert len(data_reqs) >= 1

    @pytest.mark.asyncio
    async def test_bypass_cache_still_writes_cache(self):
        rows = [_make_layer_row("1")]
        redis = _make_redis(None)
        repo, _ = _make_repo(rows, redis_client=redis)
        await repo.fetch_layers(column_filters={}, bypass_cache=True)
        redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_redis_still_works(self):
        rows = [_make_layer_row("1")]
        repo, _ = _make_repo(rows, redis_client=None)
        result = await repo.fetch_layers(column_filters={})
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Tests: user token forwarding (with_user_token)
# ---------------------------------------------------------------------------


class TestUserTokenForwarding:
    """Regression: the data-proxy rejects client_credentials on this schema
    (permission denied), so every request must carry the end-user JWT via
    ``with_user_token``."""

    def _data_requests(self, fake: FakeDataProxy) -> list[httpx.Request]:
        return [r for r in fake.requests if r.url.host != "keycloak.example"]

    @pytest.mark.asyncio
    async def test_layers_requests_carry_user_token(self):
        rows = [_make_layer_row(str(i)) for i in range(2500)]
        repo, fake = _make_repo(rows)
        await repo.fetch_layers(column_filters={}, user_token="user-jwt-123")
        for req in self._data_requests(fake):
            assert req.headers.get("authorization") == "Bearer user-jwt-123"

    @pytest.mark.asyncio
    async def test_layers_fallback_to_client_credentials_when_no_token(self):
        """user_token=None → client_credentials flow (dummy token from fake
        Keycloak), matching the pre-existing client behavior."""
        rows = [_make_layer_row("1")]
        repo, fake = _make_repo(rows)
        await repo.fetch_layers(column_filters={}, user_token=None)
        for req in self._data_requests(fake):
            assert req.headers.get("authorization") == "Bearer test-token"

    @pytest.mark.asyncio
    async def test_filter_options_carry_user_token(self):
        rows = [{"tipo_camada": "BAIRRO", "count": 1}]
        repo, fake = _make_filter_repo({"tipo_camada": rows})
        await repo.get_filter_options("tipos_camada", user_token="user-jwt-456")
        for req in self._data_requests(fake):
            assert req.headers.get("authorization") == "Bearer user-jwt-456"


# ---------------------------------------------------------------------------
# Tests: get_filter_options
# ---------------------------------------------------------------------------


class FakeFilterDataProxy:
    """Returns canned GROUP BY rows for filter-options queries."""

    def __init__(self, rows_by_col: dict[str, list[dict]]) -> None:
        self.rows_by_col = rows_by_col
        self.requests: list[httpx.Request] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "keycloak.example":
            return httpx.Response(
                200,
                json={"access_token": "test-token", "expires_in": 3600},
            )
        self.requests.append(request)
        # Extract first column from select param to determine which field
        select = request.url.params.get("select", "")
        col = select.split(",")[0] if select else ""
        rows = self.rows_by_col.get(col, [])
        return httpx.Response(200, json=rows, request=request)


def _make_filter_repo(
    rows_by_col: dict[str, list[dict]],
    redis_client=None,
) -> tuple[PostgrestGeospatialRepository, FakeFilterDataProxy]:
    fake = FakeFilterDataProxy(rows_by_col)
    client = PostgrestClient(CONFIG, transport=httpx.MockTransport(fake))
    return PostgrestGeospatialRepository(client, redis_client=redis_client), fake


class TestGetFilterOptions:
    @pytest.mark.asyncio
    async def test_returns_distinct_values(self):
        rows = [
            {"tipo_camada": "BAIRRO", "count": 100},
            {"tipo_camada": "ESCOLA", "count": 200},
        ]
        repo, _ = _make_filter_repo({"tipo_camada": rows})
        result = await repo.get_filter_options("tipos_camada")
        assert len(result) == 2
        assert all(isinstance(o, FilterOption) for o in result)
        labels = [o.label for o in result]
        assert "BAIRRO" in labels
        assert "ESCOLA" in labels

    @pytest.mark.asyncio
    async def test_unknown_field_returns_empty(self):
        repo, _ = _make_filter_repo({})
        result = await repo.get_filter_options("campo_inexistente")
        assert result == []

    @pytest.mark.asyncio
    async def test_cache_miss_writes_to_redis(self):
        rows = [{"tipo_camada": "BAIRRO", "count": 1}]
        redis = _make_redis(None)
        repo, _ = _make_filter_repo({"tipo_camada": rows}, redis_client=redis)
        await repo.get_filter_options("tipos_camada")
        redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cache_hit_skips_postgrest(self):
        cached = [{"id": "BAIRRO", "label": "BAIRRO"}]
        redis = _make_redis(cached)
        repo, fake = _make_filter_repo({}, redis_client=redis)
        result = await repo.get_filter_options("tipos_camada")
        data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
        assert len(data_reqs) == 0
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_all_valid_field_names(self):
        """All 7 field names must be accepted without error."""
        valid_fields = [
            "tipos_camada", "categorias", "regionais", "bairros",
            "regioes_administrativas", "subprefeituras", "nomes",
        ]
        col_map = {
            "tipos_camada": "tipo_camada",
            "categorias": "categoria",
            "regionais": "regional",
            "bairros": "bairro",
            "regioes_administrativas": "regiao_administrativa",
            "subprefeituras": "subprefeitura",
            "nomes": "nome",
        }
        for field in valid_fields:
            col = col_map[field]
            repo, _ = _make_filter_repo({col: [{col: "TEST", "count": 1}]})
            result = await repo.get_filter_options(field)
            assert isinstance(result, list), f"Expected list for field {field!r}"


# ---------------------------------------------------------------------------
# Tests: get_filter_vocabulary (backward compat bulk)
# ---------------------------------------------------------------------------


class TestGetFilterVocabulary:
    @pytest.mark.asyncio
    async def test_returns_all_seven_fields(self):
        """get_filter_vocabulary must populate all 7 GeospatialFilterOptions fields."""
        # All fields return one option each
        rows_by_col = {
            "tipo_camada": [{"tipo_camada": "BAIRRO", "count": 1}],
            "categoria": [{"categoria": "BAIRRO", "count": 1}],
            "regional": [{"regional": "1.0", "count": 1}],
            "bairro": [{"bairro": "CENTRO", "count": 1}],
            "regiao_administrativa": [{"regiao_administrativa": "I", "count": 1}],
            "subprefeitura": [{"subprefeitura": "CENTRO", "count": 1}],
            "nome": [{"nome": "Teste", "count": 1}],
        }
        repo, _ = _make_filter_repo(rows_by_col)
        result = await repo.get_filter_vocabulary()
        assert len(result.tipos_camada) == 1
        assert len(result.categorias) == 1
        assert len(result.regionais) == 1
        assert len(result.bairros) == 1
        assert len(result.regioes_administrativas) == 1
        assert len(result.subprefeituras) == 1
        assert len(result.nomes) == 1


# ---------------------------------------------------------------------------
# Tests: fetch_regularidade_por_camada
# ---------------------------------------------------------------------------


class FakeRegularidadeDataProxy:
    """Returns canned aggregate rows for the consolidado table."""

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
        return httpx.Response(
            200, json=self.rows_by_table.get(table, []), request=request
        )


def _make_regularidade_repo(
    rows_by_table: dict[str, list[dict]],
    redis_client=None,
) -> tuple[PostgrestGeospatialRepository, FakeRegularidadeDataProxy]:
    fake = FakeRegularidadeDataProxy(rows_by_table)
    client = PostgrestClient(CONFIG, transport=httpx.MockTransport(fake))
    return PostgrestGeospatialRepository(client, redis_client=redis_client), fake


class TestFetchRegularidadePorCamada:
    @pytest.mark.asyncio
    async def test_bairro_aggregates_from_consolidado(self):
        rows = [
            {
                "bairro": "Vargem Grande",
                "regular": 327,
                "den": 734,
                "irreg": 407,
            },
        ]
        repo, fake = _make_regularidade_repo(
            {"endpoint_participante_visao_geral_consolidado": rows}
        )
        result = await repo.fetch_regularidade_por_camada("bairro")
        assert len(result) == 1
        agg = result[0]
        assert agg.regiao == "Vargem Grande"
        assert agg.total_participantes == 734
        assert agg.total_regulares == 327
        assert agg.total_irregulares == 407
        data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
        assert len(data_reqs) == 1
        select = data_reqs[0].url.params.get("select", "")
        assert "bairro" in select

    @pytest.mark.asyncio
    async def test_ra_groups_by_regiao_administrativa(self):
        rows = [
            {
                "regiao_administrativa": "3ª Rio Comprido",
                "regular": 100,
                "den": 150,
                "irreg": 50,
            },
        ]
        repo, fake = _make_regularidade_repo(
            {"endpoint_participante_visao_geral_consolidado": rows}
        )
        result = await repo.fetch_regularidade_por_camada("ra")
        assert result[0].regiao == "3ª Rio Comprido"
        data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
        select = data_reqs[0].url.params.get("select", "")
        assert "regiao_administrativa" in select
        params = dict(data_reqs[0].url.params)
        assert params.get("regiao_administrativa") == "not.is.null"

    @pytest.mark.asyncio
    async def test_unknown_camada_raises_value_error(self):
        repo, _ = _make_regularidade_repo({})
        with pytest.raises(ValueError, match="desconhecida"):
            await repo.fetch_regularidade_por_camada("municipio")

    @pytest.mark.asyncio
    async def test_cache_miss_writes_to_redis(self):
        rows = [{"bairro": "Centro", "regular": 1, "den": 2, "irreg": 1}]
        redis = _make_redis(None)
        repo, _ = _make_regularidade_repo(
            {"endpoint_participante_visao_geral_consolidado": rows},
            redis_client=redis,
        )
        await repo.fetch_regularidade_por_camada("bairro", user_id="cpf")
        redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cache_hit_skips_postgrest(self):
        cached = [
            {
                "regiao": "Centro",
                "total_participantes": 2,
                "total_regulares": 1,
                "total_irregulares": 1,
            }
        ]
        redis = _make_redis(cached)
        repo, fake = _make_regularidade_repo({}, redis_client=redis)
        result = await repo.fetch_regularidade_por_camada("bairro", user_id="cpf")
        data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
        assert len(data_reqs) == 0
        assert result[0].regiao == "Centro"

    @pytest.mark.asyncio
    async def test_bypass_cache_still_fetches(self):
        cached = [
            {
                "regiao": "Centro",
                "total_participantes": 2,
                "total_regulares": 1,
                "total_irregulares": 1,
            }
        ]
        redis = _make_redis(cached)
        repo, fake = _make_regularidade_repo(
            {
                "endpoint_participante_visao_geral_consolidado": [
                    {"bairro": "Centro", "regular": 1, "den": 2, "irreg": 1}
                ]
            },
            redis_client=redis,
        )
        await repo.fetch_regularidade_por_camada(
            "bairro", user_id="cpf", bypass_cache=True
        )
        data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
        assert len(data_reqs) >= 1

    @pytest.mark.asyncio
    async def test_requests_carry_user_token(self):
        rows = [{"bairro": "Centro", "regular": 1, "den": 2, "irreg": 1}]
        repo, fake = _make_regularidade_repo(
            {"endpoint_participante_visao_geral_consolidado": rows}
        )
        await repo.fetch_regularidade_por_camada(
            "bairro", user_token="user-jwt-789"
        )
        data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
        for req in data_reqs:
            assert req.headers.get("authorization") == "Bearer user-jwt-789"

    @pytest.mark.asyncio
    async def test_status_multiselect_filter_applied(self):
        rows = [{"bairro": "Centro", "regular": 1, "den": 2, "irreg": 1}]
        repo, fake = _make_regularidade_repo(
            {"endpoint_participante_visao_geral_consolidado": rows}
        )
        await repo.fetch_regularidade_por_camada("bairro", status=["Ativo"])
        data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
        params = dict(data_reqs[0].url.params)
        assert params.get("pic_status") == "in.(Ativo)"

    @pytest.mark.asyncio
    async def test_cohortes_multiselect_filter_applied(self):
        rows = [{"bairro": "Centro", "regular": 1, "den": 2, "irreg": 1}]
        repo, fake = _make_regularidade_repo(
            {"endpoint_participante_visao_geral_consolidado": rows}
        )
        await repo.fetch_regularidade_por_camada(
            "bairro", cohortes=["2025-03-01", "2026-07-01"]
        )
        data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
        params = data_reqs[0].url.params
        assert params.get_list("pic_cohort") == [
            "in.(2025-03-01,2026-07-01)"
        ]

    @pytest.mark.asyncio
    async def test_cohorte_unico(self):
        rows = [{"bairro": "Centro", "regular": 1, "den": 2, "irreg": 1}]
        repo, fake = _make_regularidade_repo(
            {"endpoint_participante_visao_geral_consolidado": rows}
        )
        await repo.fetch_regularidade_por_camada(
            "bairro", cohortes=["2025-03-01"]
        )
        data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
        params = data_reqs[0].url.params
        assert params.get_list("pic_cohort") == ["in.(2025-03-01)"]

    @pytest.mark.asyncio
    async def test_protocolo_id_troca_tabela_e_metrica(self):
        rows = [
            {
                "bairro": "Vargem Grande",
                "regular": 200,
                "den": 300,
            }
        ]
        repo, fake = _make_regularidade_repo(
            {"endpoint_participante_visao_geral_protocolos": rows}
        )
        result = await repo.fetch_regularidade_por_camada(
            "bairro", protocolo_id="sms_vacinacao_pentavalente"
        )
        assert len(result) == 1
        agg = result[0]
        assert agg.total_participantes == 300
        assert agg.total_regulares == 200
        # A tabela de protocolos não tem coluna de irregulares → den - regular
        assert agg.total_irregulares == 100
        data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
        params = data_reqs[0].url.params
        assert params.get("protocolo_id") == "eq.sms_vacinacao_pentavalente"
        assert "protocolo_regular_numerador.sum()" in params.get("select", "")

    @pytest.mark.asyncio
    async def test_sem_protocolo_usa_consolidado(self):
        rows = [{"bairro": "Centro", "regular": 1, "den": 2, "irreg": 1}]
        repo, fake = _make_regularidade_repo(
            {"endpoint_participante_visao_geral_consolidado": rows}
        )
        await repo.fetch_regularidade_por_camada("bairro")
        data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
        path = data_reqs[0].url.path
        assert "visao_geral_consolidado" in path
        assert "protocolo_id" not in data_reqs[0].url.params


class TestFetchProtocolos:
    @pytest.mark.asyncio
    async def test_retorna_distintos_da_visao_geral_protocolos(self):
        rows = [
            {
                "protocolo_id": "sme_frequencia_escolar",
                "protocolo_secretaria": "SME",
                "protocolo_descricao": "Frequência escolar",
                "count": 100,
            },
            {
                "protocolo_id": "sms_vacinacao_pentavalente",
                "protocolo_secretaria": "SMS",
                "protocolo_descricao": "Vacinação",
                "count": 50,
            },
        ]
        repo, fake = _make_regularidade_repo(
            {"endpoint_participante_visao_geral_protocolos": rows}
        )
        result = await repo.fetch_protocolos()
        assert len(result) == 2
        assert result[0].protocolo_id == "sme_frequencia_escolar"
        assert result[1].protocolo_secretaria == "SMS"
        data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
        path = data_reqs[0].url.path
        assert "visao_geral_protocolos" in path

    @pytest.mark.asyncio
    async def test_cache_hit_skips_postgrest(self):
        cached = [
            {
                "protocolo_id": "sme_frequencia_escolar",
                "protocolo_secretaria": "SME",
                "protocolo_descricao": "Frequência escolar",
            }
        ]
        redis = _make_redis(cached)
        repo, fake = _make_regularidade_repo({}, redis_client=redis)
        result = await repo.fetch_protocolos(user_id="cpf")
        data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
        assert len(data_reqs) == 0
        assert result[0].protocolo_id == "sme_frequencia_escolar"


class TestFetchProtocolosPorRegiao:
    @pytest.mark.asyncio
    async def test_filtra_pela_coluna_da_camada_e_agrega(self):
        rows = [
            {
                "protocolo_id": "sms_vacinacao_pentavalente",
                "protocolo_secretaria": "SMS",
                "protocolo_descricao": "Vacinação",
                "regular": 80,
                "den": 100,
            },
            {
                "protocolo_id": "sme_frequencia_escolar",
                "protocolo_secretaria": "SME",
                "protocolo_descricao": "Frequência escolar",
                "regular": 0,
                "den": 0,
            },
        ]
        repo, fake = _make_regularidade_repo(
            {"endpoint_participante_visao_geral_protocolos": rows}
        )
        result = await repo.fetch_protocolos_por_regiao(
            camada="bairro",
            regiao="Centro",
            user_id="cpf",
            status=["Ativo"],
        )
        assert len(result) == 2
        primeiro = result[0]
        assert primeiro.protocolo_id == "sms_vacinacao_pentavalente"
        assert primeiro.total_participantes == 100
        assert primeiro.total_regulares == 80
        assert primeiro.total_irregulares == 20  # den - regular
        assert primeiro.taxa_regularidade == 80.0
        # Sem participantes → sem taxa (protocolo sem dados na região)
        assert result[1].taxa_regularidade is None

        data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
        assert len(data_reqs) == 1
        path = data_reqs[0].url.path
        assert "visao_geral_protocolos" in path
        params = dict(data_reqs[0].url.params)
        assert params.get("bairro") == "eq.Centro"
        assert params.get("pic_status") == "in.(Ativo)"
        select = params.get("select", "")
        assert "protocolo_id" in select
        assert "protocolo_regular_numerador" in select
        assert "protocolo_regular_denominador" in select

    @pytest.mark.asyncio
    async def test_ra_usa_coluna_regiao_administrativa(self):
        repo, fake = _make_regularidade_repo(
            {"endpoint_participante_visao_geral_protocolos": []}
        )
        await repo.fetch_protocolos_por_regiao(
            camada="ra", regiao="3ª Rio Comprido", cohortes=["2025-03-01"]
        )
        data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
        params = dict(data_reqs[0].url.params)
        assert params.get("regiao_administrativa") == "eq.3ª Rio Comprido"
        assert params.get("pic_cohort") == "in.(2025-03-01)"

    @pytest.mark.asyncio
    async def test_unknown_camada_raises_value_error(self):
        repo, _ = _make_regularidade_repo({})
        with pytest.raises(ValueError, match="desconhecida"):
            await repo.fetch_protocolos_por_regiao(camada="municipio", regiao="X")

    @pytest.mark.asyncio
    async def test_ignora_linhas_sem_protocolo_id(self):
        rows = [
            {"protocolo_id": None, "regular": 1, "den": 1},
            {
                "protocolo_id": "sms_vacinacao_pentavalente",
                "protocolo_secretaria": "SMS",
                "protocolo_descricao": "Vacinação",
                "regular": 5,
                "den": 10,
            },
        ]
        repo, _ = _make_regularidade_repo(
            {"endpoint_participante_visao_geral_protocolos": rows}
        )
        result = await repo.fetch_protocolos_por_regiao(camada="bairro", regiao="X")
        assert [p.protocolo_id for p in result] == ["sms_vacinacao_pentavalente"]

    @pytest.mark.asyncio
    async def test_cache_miss_writes_to_redis(self):
        rows = [
            {
                "protocolo_id": "sms_vacinacao_pentavalente",
                "protocolo_secretaria": "SMS",
                "protocolo_descricao": "Vacinação",
                "regular": 5,
                "den": 10,
            }
        ]
        redis = _make_redis(None)
        repo, _ = _make_regularidade_repo(
            {"endpoint_participante_visao_geral_protocolos": rows},
            redis_client=redis,
        )
        await repo.fetch_protocolos_por_regiao(
            camada="bairro", regiao="Centro", user_id="cpf"
        )
        redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cache_hit_skips_postgrest(self):
        cached = [
            {
                "protocolo_id": "sms_vacinacao_pentavalente",
                "protocolo_secretaria": "SMS",
                "protocolo_descricao": "Vacinação",
                "total_participantes": 10,
                "total_regulares": 5,
                "total_irregulares": 5,
                "taxa_regularidade": 50.0,
            }
        ]
        redis = _make_redis(cached)
        repo, fake = _make_regularidade_repo({}, redis_client=redis)
        result = await repo.fetch_protocolos_por_regiao(
            camada="bairro", regiao="Centro", user_id="cpf"
        )
        data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
        assert len(data_reqs) == 0
        assert result[0].protocolo_id == "sms_vacinacao_pentavalente"
        assert result[0].taxa_regularidade == 50.0


class TestFetchProtocoloGeral:
    @pytest.mark.asyncio
    async def test_agrega_protocolo_sem_filtro_de_regiao(self):
        rows = [{"regular": 996, "den": 1000}]
        repo, fake = _make_regularidade_repo(
            {"endpoint_participante_visao_geral_protocolos": rows}
        )
        result = await repo.fetch_protocolo_geral(
            protocolo_id="smas_acesso_alimentacao",
            user_id="cpf",
            status=["Ativo"],
        )
        assert result is not None
        assert result.total_participantes == 1000
        assert result.total_regulares == 996
        assert result.total_irregulares == 4  # den - regular
        assert result.taxa_regularidade == 99.6

        data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
        assert len(data_reqs) == 1
        params = dict(data_reqs[0].url.params)
        assert params.get("protocolo_id") == "eq.smas_acesso_alimentacao"
        assert params.get("pic_status") == "in.(Ativo)"
        # Sem coluna de região na query
        for col in ("bairro", "regiao_administrativa", "id_cas", "id_cre", "id_ap"):
            assert col not in params

    @pytest.mark.asyncio
    async def test_sem_linhas_retorna_none(self):
        repo, _ = _make_regularidade_repo(
            {"endpoint_participante_visao_geral_protocolos": []}
        )
        result = await repo.fetch_protocolo_geral(protocolo_id="inexistente")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_hit_skips_postgrest(self):
        cached = {
            "total_participantes": 1000,
            "total_regulares": 996,
            "total_irregulares": 4,
            "taxa_regularidade": 99.6,
        }
        redis = _make_redis(cached)
        repo, fake = _make_regularidade_repo({}, redis_client=redis)
        result = await repo.fetch_protocolo_geral(
            protocolo_id="smas_acesso_alimentacao", user_id="cpf"
        )
        data_reqs = [r for r in fake.requests if r.url.host != "keycloak.example"]
        assert len(data_reqs) == 0
        assert result is not None
        assert result.taxa_regularidade == 99.6

    @pytest.mark.asyncio
    async def test_cache_miss_writes_to_redis(self):
        rows = [{"regular": 1, "den": 2}]
        redis = _make_redis(None)
        repo, _ = _make_regularidade_repo(
            {"endpoint_participante_visao_geral_protocolos": rows},
            redis_client=redis,
        )
        await repo.fetch_protocolo_geral(
            protocolo_id="smas_acesso_alimentacao", user_id="cpf"
        )
        redis.set.assert_awaited_once()

    def test_cache_key_depende_de_protocolo_e_filtros(self):
        from src.pic.infrastructure.repositories.postgrest_geospatial_repository import (
            _make_protocolo_geral_cache_key,
        )

        base = _make_protocolo_geral_cache_key("p1", "u")
        assert base != _make_protocolo_geral_cache_key("p2", "u")
        assert base != _make_protocolo_geral_cache_key("p1", "u2")
        assert base != _make_protocolo_geral_cache_key("p1", "u", status=["Ativo"])
        # Ordem das listas não altera a chave
        assert _make_protocolo_geral_cache_key(
            "p1", "u", cohortes=["a", "b"]
        ) == _make_protocolo_geral_cache_key("p1", "u", cohortes=["b", "a"])


class TestRegularidadeCacheKey:
    def test_key_depends_on_camada_and_user(self):
        from src.pic.infrastructure.repositories.postgrest_geospatial_repository import (
            _make_regularidade_cache_key,
        )

        assert _make_regularidade_cache_key("bairro", "a") != _make_regularidade_cache_key(
            "ra", "a"
        )
        assert _make_regularidade_cache_key("bairro", "a") != _make_regularidade_cache_key(
            "bairro", "b"
        )
        assert _make_regularidade_cache_key("bairro", "a") == _make_regularidade_cache_key(
            "bairro", "a"
        )

    def test_key_depends_on_filters(self):
        from src.pic.infrastructure.repositories.postgrest_geospatial_repository import (
            _make_regularidade_cache_key,
        )

        base = _make_regularidade_cache_key("bairro", "a")
        assert base != _make_regularidade_cache_key("bairro", "a", status=["Ativo"])
        assert base != _make_regularidade_cache_key(
            "bairro", "a", cohortes=["2025-03-01"]
        )
        assert base != _make_regularidade_cache_key(
            "bairro", "a", cohortes=["2025-03-01", "2025-04-01"]
        )
        assert base != _make_regularidade_cache_key(
            "bairro", "a", protocolo_id="sms_vacinacao_pentavalente"
        )
        assert _make_regularidade_cache_key(
            "bairro", "a", status=["Ativo"], cohortes=["2025-03-01"]
        ) == _make_regularidade_cache_key(
            "bairro", "a", status=["Ativo"], cohortes=["2025-03-01"]
        )
        # Ordem das listas não altera a chave (multiselect)
        assert _make_regularidade_cache_key(
            "bairro", "a", cohortes=["2025-03-01", "2025-04-01"]
        ) == _make_regularidade_cache_key(
            "bairro", "a", cohortes=["2025-04-01", "2025-03-01"]
        )


# ---------------------------------------------------------------------------
# Tests: cache key helpers
# ---------------------------------------------------------------------------


class TestCacheKeys:
    def test_layers_key_deterministic(self):
        k1 = _make_layers_cache_key({"tipo_camada": "BAIRRO"})
        k2 = _make_layers_cache_key({"tipo_camada": "BAIRRO"})
        assert k1 == k2

    def test_layers_key_changes_with_filters(self):
        k1 = _make_layers_cache_key({"tipo_camada": "BAIRRO"})
        k2 = _make_layers_cache_key({"tipo_camada": "ESCOLA"})
        assert k1 != k2

    def test_layers_empty_filters_vs_none_are_different(self):
        k1 = _make_layers_cache_key({})
        k2 = _make_layers_cache_key({"tipo_camada": "X"})
        assert k1 != k2

    def test_filter_key_deterministic(self):
        k1 = _make_filter_cache_key("tipos_camada", {"tipo_camada": "BAIRRO"})
        k2 = _make_filter_cache_key("tipos_camada", {"tipo_camada": "BAIRRO"})
        assert k1 == k2

    def test_filter_key_changes_with_field(self):
        k1 = _make_filter_cache_key("tipos_camada", {})
        k2 = _make_filter_cache_key("categorias", {})
        assert k1 != k2

    def test_filter_key_changes_with_filters(self):
        k1 = _make_filter_cache_key("tipos_camada", {"regional": "1.0"})
        k2 = _make_filter_cache_key("tipos_camada", {"regional": "2.0"})
        assert k1 != k2

    def test_layers_key_has_no_user_dimension(self):
        """Geospatial cache keys must NOT depend on user — no RLS."""
        # Both calls with same filters should produce the same key regardless
        # of who makes the call (no user param in the key function)
        k1 = _make_layers_cache_key({"tipo_camada": "BAIRRO"})
        k2 = _make_layers_cache_key({"tipo_camada": "BAIRRO"})
        assert k1 == k2  # trivially true, but documents the intention
