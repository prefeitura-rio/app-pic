"""PostgREST implementation of IGeospatialRepository.

Replaces BigQueryGeospatialRepository for the two geospatial operations:
  - fetch_layers  → GET /endpoint_camadas_geoespaciais (4470+ rows, paged)
  - get_filter_options → per-field lazy vocabulary (like participants)

Design notes:

- The table has 4470+ rows; PostgREST caps at 1000 per response (PGRST_DB_MAX_ROWS).
  We resolve this with a *rolling-window concurrent fetch*: pages are fetched in
  windows of FETCH_WINDOW (default 2) simultaneous asyncio.gather calls until no
  more pages are returned.  This is equivalent to the export_wide_rows approach in
  the participant repository, but simpler because there is no ContextVar / user
  token involved (geospatial has no RLS).

- Cache is Redis-keyed by a deterministic hash of the active column_filters (or
  field + filters for vocabulary queries). The cache key does NOT include the
  user id because geospatial data is not user-scoped (no RLS, no secretaria
  filtering). TTL is 1800 s (30 min), matching the participant repository.

- Prefer: count=exact is requested on the first page so we know the total row
  count upfront and can calculate the exact number of pages needed, avoiding a
  final "short page" check.

- get_filter_options mirrors the participant repository's per-field approach:
  one PostgREST GROUP-BY query (select=<col>,count()&group_by=<col>) per field,
  returning distinct non-null values sorted alphabetically.  Active filters
  (cascade) are forwarded so the returned options reflect the current filter state.

- The old get_filter_vocabulary (bulk vocabulary) is kept for backward compat but
  internally calls get_filter_options for each field and assembles the full
  GeospatialFilterOptions object.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any

from src.pic.application.ports.geospatial_repository import IGeospatialRepository
from src.pic.domain.models.filters import FilterOption
from src.pic.domain.models.geospatial import (
    GeospatialFilterOptions,
    GeospatialLayer,
)
from src.pic.infrastructure.postgrest_client.client import PostgrestClient
from src.utils.log import logger

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TABLE = "endpoint_camadas_geoespaciais"

# Pages fetched concurrently per window (rolling window strategy)
_FETCH_WINDOW = 2

# PostgREST page size (must not exceed PGRST_DB_MAX_ROWS on the server)
_PAGE_SIZE = 1000

# Redis TTL (seconds) — same as participant repository
_CACHE_TTL = 1800

_LAYERS_CACHE_PREFIX = "geospatial_layers:"
_FILTER_CACHE_PREFIX = "geospatial_filter_options:"

# Columns that map to each filter-option field name
_FIELD_COLUMN: dict[str, str] = {
    "tipos_camada": "tipo_camada",
    "categorias": "categoria",
    "regionais": "regional",
    "bairros": "bairro",
    "regioes_administrativas": "regiao_administrativa",
    "subprefeituras": "subprefeitura",
    "nomes": "nome",
}

# Columns selected for a layer row. `geometry` already comes from PostgREST
# as a GeoJSON object; the repo serializes it into the `geometry_geojson`
# string the API contract exposes (parity with BigQuery's ST_AsGeoJSON).
_LAYER_SELECT = (
    "tipo_camada,tipo_geometria,categoria,id,id_unico,nome,"
    "geometry,regional,bairro,regiao_administrativa,"
    "subprefeitura,metadata"
)

# Order matches the legacy BigQuery query (tipo_camada, categoria, nome) with
# id_unico as a stable pagination tiebreaker.
_LAYER_ORDER = ["tipo_camada", "categoria", "nome", "id_unico"]

# ---------------------------------------------------------------------------
# Cache key helpers
# ---------------------------------------------------------------------------


def _make_layers_cache_key(column_filters: dict[str, object]) -> str:
    payload = json.dumps(column_filters, sort_keys=True, default=str)
    return _LAYERS_CACHE_PREFIX + hashlib.sha256(payload.encode()).hexdigest()


def _make_filter_cache_key(field: str, column_filters: dict[str, object]) -> str:
    payload = json.dumps(
        {"field": field, "filters": column_filters}, sort_keys=True, default=str
    )
    return _FILTER_CACHE_PREFIX + hashlib.sha256(payload.encode()).hexdigest()


# ---------------------------------------------------------------------------
# PostgREST query helpers
# ---------------------------------------------------------------------------


def _apply_filters(query: Any, column_filters: dict[str, object]) -> Any:
    """Apply column_filters to a PostgREST query builder.

    Each value can be:
      - a plain str/int/bool scalar  → eq.<value>
      - a list of scalars            → in.(<v1>,<v2>,...)
    """
    for column, value in column_filters.items():
        if isinstance(value, list):
            query = query.in_(column, value)
        else:
            query = query.eq(column, value)
    return query


def _row_to_layer(row: dict[str, Any]) -> GeospatialLayer:
    """Map a PostgREST row to a GeospatialLayer.

    PostgREST returns `geometry` as a GeoJSON object; the API contract
    exposes it as a JSON string in `geometry_geojson` (parity with
    BigQuery's ST_AsGeoJSON).  `id` is coerced to string for contract
    stability (Postgres may store it as bigint).
    """
    data = dict(row)
    geometry = data.pop("geometry", None)
    if isinstance(geometry, str):
        data["geometry_geojson"] = geometry
    elif geometry is not None:
        data["geometry_geojson"] = json.dumps(geometry)
    else:
        data["geometry_geojson"] = None

    if data.get("id") is not None:
        data["id"] = str(data["id"])

    return GeospatialLayer(**data)


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class PostgrestGeospatialRepository(IGeospatialRepository):
    """PostgREST-backed geospatial repository.

    Args:
        client: Authenticated PostgREST client (singleton, no user token needed
            for geospatial — there is no RLS on this table).
        redis_client: Optional Redis client; when absent, caching is disabled
            and every request goes to PostgREST.
    """

    def __init__(
        self,
        client: PostgrestClient,
        redis_client: Any = None,
    ) -> None:
        self._client = client
        self._redis = redis_client

    # ------------------------------------------------------------------
    # IGeospatialRepository — layers
    # ------------------------------------------------------------------

    async def fetch_layers(
        self,
        column_filters: dict[str, object],
        user_token: str | None = None,
        bypass_cache: bool = False,
    ) -> list[GeospatialLayer]:
        """Fetch all geospatial layers matching *column_filters*.

        Uses a rolling-window of ``_FETCH_WINDOW`` concurrent PostgREST requests
        to overcome the 1000-row cap, then assembles and caches the full result.

        Cache key is derived from *column_filters* only (no user dimension —
        the table has no RLS, so the result is the same for every authenticated
        user with the same filters).
        """
        cache_key = _make_layers_cache_key(column_filters)

        if not bypass_cache:
            cached = await self._get_layers_from_cache(cache_key)
            if cached is not None:
                return cached

        async with self._client.with_user_token(user_token):
            layers = await self._fetch_all_pages(column_filters)

        await self._set_layers_cache(cache_key, layers)
        logger.info(
            f"[geospatial] layers fetched: {len(layers)} rows, "
            f"filters={list(column_filters.keys())}"
        )
        return layers

    # ------------------------------------------------------------------
    # IGeospatialRepository — per-field filter vocabulary (lazy)
    # ------------------------------------------------------------------

    async def get_filter_options(
        self,
        field: str,
        column_filters: dict[str, object] | None = None,
        user_token: str | None = None,
        bypass_cache: bool = False,
    ) -> list[FilterOption]:
        """Return distinct non-null values for *field*, respecting active filters.

        *field* is the external field name (e.g. ``"tipos_camada"``), which maps
        to the PostgREST column via ``_FIELD_COLUMN``.  Active *column_filters*
        (cascade) are forwarded so the options reflect the current filter state
        (same semantic as the participant repository's per-field vocabulary).
        """
        if field not in _FIELD_COLUMN:
            logger.warning(f"[geospatial] unknown filter field: {field!r}")
            return []

        filters = column_filters or {}
        cache_key = _make_filter_cache_key(field, filters)

        if not bypass_cache:
            cached = await self._get_filter_from_cache(cache_key)
            if cached is not None:
                return cached

        async with self._client.with_user_token(user_token):
            options = await self._fetch_filter_options(field, filters)

        await self._set_filter_cache(cache_key, options)
        logger.info(
            f"[geospatial] filter options for {field!r}: "
            f"{len(options)} values, filters={list(filters.keys())}"
        )
        return options

    # ------------------------------------------------------------------
    # IGeospatialRepository — bulk vocabulary (backward compat)
    # ------------------------------------------------------------------

    async def get_filter_vocabulary(
        self,
        user_token: str | None = None,
        bypass_cache: bool = False,
    ) -> GeospatialFilterOptions:
        """Return the full filter vocabulary (all fields at once).

        Kept for backward compatibility with the BigQuery-backed endpoint.
        Internally calls get_filter_options for each of the 7 fields
        concurrently and assembles the GeospatialFilterOptions object.
        """
        fields = list(_FIELD_COLUMN.keys())
        results = await asyncio.gather(
            *(
                self.get_filter_options(
                    f, column_filters={}, user_token=user_token, bypass_cache=bypass_cache
                )
                for f in fields
            )
        )
        field_options = dict(zip(fields, results, strict=True))
        return GeospatialFilterOptions(
            tipos_camada=field_options.get("tipos_camada", []),
            categorias=field_options.get("categorias", []),
            regionais=field_options.get("regionais", []),
            bairros=field_options.get("bairros", []),
            regioes_administrativas=field_options.get("regioes_administrativas", []),
            subprefeituras=field_options.get("subprefeituras", []),
            nomes=field_options.get("nomes", []),
        )

    # ------------------------------------------------------------------
    # Internal: rolling-window concurrent page fetcher
    # ------------------------------------------------------------------

    async def _fetch_all_pages(
        self, column_filters: dict[str, object]
    ) -> list[GeospatialLayer]:
        """Fetch all pages of endpoint_camadas_geoespaciais concurrently.

        Must be called inside a ``with_user_token`` context block so every
        concurrent request in the rolling window carries the same user JWT.

        Strategy:
          1. Fetch page 0 with ``Prefer: count=exact`` to learn the total row
             count, then derive the number of additional pages needed.
          2. Fetch remaining pages in rolling windows of ``_FETCH_WINDOW``
             concurrent requests with ``asyncio.gather``.
          3. Concatenate all results in offset order.
        """
        # --- First page (count=exact to know total) ---
        first_resp = await self._execute_page(
            column_filters=column_filters,
            offset=0,
            count="exact",
        )
        first_rows: list[dict] = first_resp.data or []
        total_count: int = first_resp.count or len(first_rows)

        layers = [_row_to_layer(row) for row in first_rows]

        if len(first_rows) == 0 or total_count <= _PAGE_SIZE:
            return layers

        # --- Calculate remaining pages ---
        remaining_offsets = list(
            range(_PAGE_SIZE, total_count, _PAGE_SIZE)
        )

        # --- Rolling window: fetch _FETCH_WINDOW pages at a time ---
        for window_start in range(0, len(remaining_offsets), _FETCH_WINDOW):
            window_offsets = remaining_offsets[window_start: window_start + _FETCH_WINDOW]
            responses = await asyncio.gather(
                *(
                    self._execute_page(column_filters=column_filters, offset=off)
                    for off in window_offsets
                )
            )
            for resp in responses:
                layers.extend(_row_to_layer(row) for row in (resp.data or []))

        return layers

    async def _execute_page(
        self,
        column_filters: dict[str, object],
        offset: int,
        count: str | None = None,
    ):
        """Execute a single page request against PostgREST.

        Caller is responsible for wrapping this in ``with_user_token``.
        """
        query = self._client.table(_TABLE).select(_LAYER_SELECT, count=count)
        query = _apply_filters(query, column_filters)
        for column in _LAYER_ORDER:
            query = query.order(column)
        query = query.offset(offset).limit(_PAGE_SIZE)
        return await query.execute()

    # ------------------------------------------------------------------
    # Internal: per-field filter options
    # ------------------------------------------------------------------

    async def _fetch_filter_options(
        self, field: str, column_filters: dict[str, object]
    ) -> list[FilterOption]:
        """Query PostgREST for distinct non-null values of the field's column.

        Caller is responsible for wrapping this in ``with_user_token``.

        Uses GROUP BY via PostgREST's aggregate syntax:
            select=<col>,count()&<col>=not.is.null
        Active column_filters are forwarded for cascade filtering.
        """
        col = _FIELD_COLUMN[field]
        # PostgREST aggregate: select=col,count() + group_by implicit via count()
        query = self._client.table(_TABLE).select(f"{col},count()")
        # Exclude NULLs from vocabulary
        query = query.not_.is_(col, "null")
        # Apply active cascade filters (exclude the field's own filter so the
        # user sees all values that *could* be selected, not just the current one)
        cascade = {k: v for k, v in column_filters.items() if k != col}
        query = _apply_filters(query, cascade)
        query = query.order(col)
        # GROUP BY is triggered implicitly when count() is in select
        resp = await query.execute()
        rows: list[dict] = resp.data or []
        return [
            FilterOption(id=str(row[col]), label=str(row[col]))
            for row in rows
            if row.get(col) is not None
        ]

    # ------------------------------------------------------------------
    # Redis helpers — layers
    # ------------------------------------------------------------------

    async def _get_layers_from_cache(self, key: str) -> list[GeospatialLayer] | None:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(key)
            if raw is None:
                return None
            data = json.loads(raw)
            layers = [GeospatialLayer.model_validate(item) for item in data]
            logger.info(f"[geospatial] layers cache HIT ({len(layers)} rows)")
            return layers
        except Exception as exc:
            logger.warning(f"[geospatial] layers cache read error (ignoring): {exc}")
            return None

    async def _set_layers_cache(
        self, key: str, layers: list[GeospatialLayer]
    ) -> None:
        if self._redis is None:
            return
        try:
            payload = json.dumps([layer.model_dump(mode="json") for layer in layers])
            await self._redis.set(key, payload, ex=_CACHE_TTL)
            logger.info(
                f"[geospatial] layers cache SET ({len(layers)} rows, TTL {_CACHE_TTL}s)"
            )
        except Exception as exc:
            logger.warning(f"[geospatial] layers cache write error (ignoring): {exc}")

    # ------------------------------------------------------------------
    # Redis helpers — filter options
    # ------------------------------------------------------------------

    async def _get_filter_from_cache(self, key: str) -> list[FilterOption] | None:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(key)
            if raw is None:
                return None
            logger.info("[geospatial] filter cache HIT")
            return [FilterOption.model_validate(item) for item in json.loads(raw)]
        except Exception as exc:
            logger.warning(f"[geospatial] filter cache read error (ignoring): {exc}")
            return None

    async def _set_filter_cache(
        self, key: str, options: list[FilterOption]
    ) -> None:
        if self._redis is None:
            return
        try:
            payload = json.dumps([opt.model_dump(mode="json") for opt in options])
            await self._redis.set(key, payload, ex=_CACHE_TTL)
            logger.info(f"[geospatial] filter cache SET (TTL {_CACHE_TTL}s)")
        except Exception as exc:
            logger.warning(f"[geospatial] filter cache write error (ignoring): {exc}")
