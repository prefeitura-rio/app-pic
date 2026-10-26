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
    CAMADA_GROUP_COLUMN,
    CamadaRegularidadeAggregate,
    GeospatialFilterOptions,
    GeospatialLayer,
    ProtocoloOption,
    RegiaoProtocoloAggregate,
    RegiaoRegularidadeResumo,
)
from src.pic.infrastructure.postgrest_client.client import PostgrestClient
from src.utils.log import logger

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TABLE = "endpoint_camadas_geoespaciais"

# Tabela consolidado do dashboard (RLS nas 7 colunas de unidade). É a mesma
# fonte das métricas da Visão Geral: participantes regulares/irregulares por
# bairro (participante_regular_numerador/denominador).
_BAIRROS_TABLE = "endpoint_participante_visao_geral_consolidado"

# Mesmo cubo do consolidado, com granularidade de protocolo (FR-007 do fluxo
# de mapas): métrica própria por protocolo (protocolo_regular_numerador/
# denominador) — usada quando protocolo_id está selecionado.
_PROTOCOLOS_TABLE = "endpoint_participante_visao_geral_protocolos"

# Pages fetched concurrently per window (rolling window strategy)
_FETCH_WINDOW = 2

# PostgREST page size (must not exceed PGRST_DB_MAX_ROWS on the server)
_PAGE_SIZE = 1000

# Redis TTL (seconds) — same as participant repository
_CACHE_TTL = 1800

# Regularidade por camada territorial: TTL igual ao dashboard (30 min). A
# resposta varia por usuário (RLS) e por camada, então a chave inclui ambos.
_REGULARIDADE_CACHE_TTL = 1800

_LAYERS_CACHE_PREFIX = "geospatial_layers:"
_FILTER_CACHE_PREFIX = "geospatial_filter_options:"
_REGULARIDADE_CACHE_PREFIX = "geospatial_regularidade:v3:"
_PROTOCOLOS_CACHE_PREFIX = "geospatial_protocolos:v1:"
_PROTOCOLOS_REGIAO_CACHE_PREFIX = "geospatial_protocolos_regiao:v1:"
_PROTOCOLO_GERAL_CACHE_PREFIX = "geospatial_protocolo_geral:v1:"

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


def _make_regularidade_cache_key(
    camada: str,
    user_id: str | None,
    status: list[str] | None = None,
    cohortes: list[str] | None = None,
    protocolo_id: str | None = None,
) -> str:
    """Cache key por camada + usuário + filtros: a RLS e os filtros mudam o resultado."""
    payload = json.dumps(
        {
            "camada": camada,
            "user_id": user_id,
            "status": sorted(status) if status else None,
            "cohortes": sorted(cohortes) if cohortes else None,
            "protocolo_id": protocolo_id,
        },
        sort_keys=True,
        default=str,
    )
    return _REGULARIDADE_CACHE_PREFIX + hashlib.sha256(payload.encode()).hexdigest()


def _make_protocolos_cache_key(user_id: str | None) -> str:
    payload = json.dumps({"user_id": user_id}, sort_keys=True, default=str)
    return _PROTOCOLOS_CACHE_PREFIX + hashlib.sha256(payload.encode()).hexdigest()


def _make_protocolos_regiao_cache_key(
    camada: str,
    regiao: str,
    user_id: str | None,
    status: list[str] | None = None,
    cohortes: list[str] | None = None,
) -> str:
    """Cache key dos protocolos de uma região: camada + valor raw + usuário + filtros."""
    payload = json.dumps(
        {
            "camada": camada,
            "regiao": regiao,
            "user_id": user_id,
            "status": sorted(status) if status else None,
            "cohortes": sorted(cohortes) if cohortes else None,
        },
        sort_keys=True,
        default=str,
    )
    return _PROTOCOLOS_REGIAO_CACHE_PREFIX + hashlib.sha256(payload.encode()).hexdigest()


def _make_protocolo_geral_cache_key(
    protocolo_id: str,
    user_id: str | None,
    status: list[str] | None = None,
    cohortes: list[str] | None = None,
) -> str:
    """Cache key da média geral do protocolo (igual para qualquer região)."""
    payload = json.dumps(
        {
            "protocolo_id": protocolo_id,
            "user_id": user_id,
            "status": sorted(status) if status else None,
            "cohortes": sorted(cohortes) if cohortes else None,
        },
        sort_keys=True,
        default=str,
    )
    return _PROTOCOLO_GERAL_CACHE_PREFIX + hashlib.sha256(payload.encode()).hexdigest()


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
    # IGeospatialRepository — regularidade por camada territorial
    # ------------------------------------------------------------------

    async def fetch_regularidade_por_camada(
        self,
        camada: str,
        user_token: str | None = None,
        user_id: str | None = None,
        bypass_cache: bool = False,
        status: list[str] | None = None,
        cohortes: list[str] | None = None,
        protocolo_id: str | None = None,
    ) -> list[CamadaRegularidadeAggregate]:
        """Agrega participantes regulares/irregulares por região da camada.

        Mesma métrica do dashboard (tabela consolidado): a RLS das 7 colunas
        de unidade é aplicada ANTES do GROUP BY, então o resultado respeita o
        escopo de permissões do usuário.

        ``camada`` seleciona a coluna do GROUP BY (``CAMADA_GROUP_COLUMN``):
        bairro → ``bairro``, ra → ``regiao_administrativa``, cas/cre/ap →
        ``id_cas``/``id_cre``/``id_ap``.

        Filtros opcionais aplicados como WHERE no PostgREST (antes do GROUP BY,
        multiselect — mesmo padrão da Visão Geral): ``status`` (lista) →
        ``pic_status=in``; ``cohortes`` (lista de ``"YYYY-MM-DD"``) →
        ``pic_cohort=in``; ``protocolo_id`` troca a fonte para
        ``endpoint_participante_visao_geral_protocolos`` com a métrica própria
        do protocolo (``protocolo_regular_*`` — FR-007).

        Sem ``protocolo_id``: ``regular`` soma ``participante_regular_numerador``
        (Regular + Atenção) e ``den`` soma ``participante_regular_denominador``
        (total de participantes) — mesma semântica do dashboard. Com
        ``protocolo_id``: ``total_irregulares`` = ``den - regular`` (a tabela
        de protocolos não tem coluna de irregulares).

        Cache Redis por camada + usuário + filtros (a resposta varia por RLS
        e pelos filtros), TTL 30 min — mesmo padrão do dashboard.
        """
        group_column = CAMADA_GROUP_COLUMN.get(camada)
        if group_column is None:
            raise ValueError(f"Camada territorial desconhecida: {camada!r}")

        cache_key = _make_regularidade_cache_key(
            camada, user_id, status, cohortes, protocolo_id
        )

        if not bypass_cache:
            cached = await self._get_regularidade_from_cache(cache_key)
            if cached is not None:
                return cached

        if protocolo_id:
            table = _PROTOCOLOS_TABLE
            select = (
                f"{group_column},"
                "regular:protocolo_regular_numerador.sum(),"
                "den:protocolo_regular_denominador.sum()"
            )
        else:
            table = _BAIRROS_TABLE
            select = (
                f"{group_column},"
                "regular:participante_regular_numerador.sum(),"
                "den:participante_regular_denominador.sum(),"
                "irreg:participante_irregular_numerador.sum()"
            )

        async with self._client.with_user_token(user_token):
            query = self._client.table(table).select(select)
            query = query.not_.is_(group_column, "null")
            if protocolo_id:
                query = query.eq("protocolo_id", protocolo_id)
            if status:
                query = query.in_("pic_status", status)
            if cohortes:
                query = query.in_("pic_cohort", cohortes)
            resp = await query.execute()

        rows: list[dict] = resp.data or []
        if protocolo_id:
            aggregates = [
                CamadaRegularidadeAggregate(
                    regiao=str(row[group_column]),
                    total_participantes=int(row.get("den") or 0),
                    total_regulares=int(row.get("regular") or 0),
                    total_irregulares=(
                        int(row.get("den") or 0) - int(row.get("regular") or 0)
                    ),
                )
                for row in rows
            ]
        else:
            aggregates = [
                CamadaRegularidadeAggregate(
                    regiao=str(row[group_column]),
                    total_participantes=int(row.get("den") or 0),
                    total_regulares=int(row.get("regular") or 0),
                    total_irregulares=int(row.get("irreg") or 0),
                )
                for row in rows
            ]

        await self._set_regularidade_cache(cache_key, aggregates)
        logger.info(
            f"[geospatial] regularidade camada={camada!r}: "
            f"{len(aggregates)} regiões user_id={user_id!r} "
            f"status={status!r} cohortes={cohortes!r} "
            f"protocolo={protocolo_id!r}"
        )
        return aggregates

    # ------------------------------------------------------------------
    # IGeospatialRepository — vocabulário de protocolos (fase 3e)
    # ------------------------------------------------------------------

    async def fetch_protocolos(
        self,
        user_token: str | None = None,
        user_id: str | None = None,
        bypass_cache: bool = False,
    ) -> list[ProtocoloOption]:
        """Distintos protocolos da visão geral de protocolos (RLS respeitada).

        GROUP BY via ``count()`` no select (mesmo padrão do filter-options).
        Cache Redis por usuário (o conjunto visível varia por RLS).
        """
        cache_key = _make_protocolos_cache_key(user_id)

        if not bypass_cache:
            cached = await self._get_protocolos_from_cache(cache_key)
            if cached is not None:
                return cached

        async with self._client.with_user_token(user_token):
            query = self._client.table(_PROTOCOLOS_TABLE).select(
                "protocolo_id,protocolo_secretaria,protocolo_descricao,count()"
            )
            query = query.not_.is_("protocolo_id", "null")
            query = query.order("protocolo_secretaria").order("protocolo_id")
            resp = await query.execute()

        rows: list[dict] = resp.data or []
        protocolos = [
            ProtocoloOption(
                protocolo_id=str(row["protocolo_id"]),
                protocolo_secretaria=row.get("protocolo_secretaria"),
                protocolo_descricao=row.get("protocolo_descricao"),
            )
            for row in rows
            if row.get("protocolo_id") is not None
        ]

        await self._set_protocolos_cache(cache_key, protocolos)
        logger.info(
            f"[geospatial] protocolos: {len(protocolos)} user_id={user_id!r}"
        )
        return protocolos

    # ------------------------------------------------------------------
    # IGeospatialRepository — protocolos de uma região (fase 3j)
    # ------------------------------------------------------------------

    async def fetch_protocolos_por_regiao(
        self,
        camada: str,
        regiao: str,
        user_token: str | None = None,
        user_id: str | None = None,
        bypass_cache: bool = False,
        status: list[str] | None = None,
        cohortes: list[str] | None = None,
    ) -> list[RegiaoProtocoloAggregate]:
        """Métricas de todos os protocolos numa região (valor RAW da coluna).

        GROUP BY protocolo_id/secretaria/descricao com filtro ``eq`` na coluna
        da camada — consulta pequena (≤ número de protocolos), uma página.
        ``total_irregulares`` = den − regular (a tabela de protocolos não tem
        coluna de irregulares — mesmo padrão do fetch_regularidade_por_camada).
        """
        group_column = CAMADA_GROUP_COLUMN.get(camada)
        if group_column is None:
            raise ValueError(f"Camada territorial desconhecida: {camada!r}")

        cache_key = _make_protocolos_regiao_cache_key(
            camada, regiao, user_id, status, cohortes
        )

        if not bypass_cache:
            cached = await self._get_protocolos_regiao_from_cache(cache_key)
            if cached is not None:
                return cached

        async with self._client.with_user_token(user_token):
            query = self._client.table(_PROTOCOLOS_TABLE).select(
                "protocolo_id,protocolo_secretaria,protocolo_descricao,"
                "regular:protocolo_regular_numerador.sum(),"
                "den:protocolo_regular_denominador.sum()"
            )
            query = query.eq(group_column, regiao)
            if status:
                query = query.in_("pic_status", status)
            if cohortes:
                query = query.in_("pic_cohort", cohortes)
            resp = await query.execute()

        protocolos: list[RegiaoProtocoloAggregate] = []
        for row in resp.data or []:
            if row.get("protocolo_id") is None:
                continue
            den = int(row.get("den") or 0)
            regular = int(row.get("regular") or 0)
            protocolos.append(
                RegiaoProtocoloAggregate(
                    protocolo_id=str(row["protocolo_id"]),
                    protocolo_secretaria=row.get("protocolo_secretaria"),
                    protocolo_descricao=row.get("protocolo_descricao"),
                    total_participantes=den,
                    total_regulares=regular,
                    total_irregulares=den - regular,
                    taxa_regularidade=(
                        round(regular / den * 100, 1) if den > 0 else None
                    ),
                )
            )

        await self._set_protocolos_regiao_cache(cache_key, protocolos)
        logger.info(
            f"[geospatial] protocolos por região camada={camada!r} "
            f"regiao={regiao!r}: {len(protocolos)} user_id={user_id!r} "
            f"status={status!r} cohortes={cohortes!r}"
        )
        return protocolos

    # ------------------------------------------------------------------
    # IGeospatialRepository — média geral de um protocolo (fase 3k)
    # ------------------------------------------------------------------

    async def fetch_protocolo_geral(
        self,
        protocolo_id: str,
        user_token: str | None = None,
        user_id: str | None = None,
        bypass_cache: bool = False,
        status: list[str] | None = None,
        cohortes: list[str] | None = None,
    ) -> RegiaoRegularidadeResumo | None:
        """Agrega um protocolo em TODAS as regiões (sem filtro de região).

        Consulta de UMA linha (somas do protocolo + filtros); o resultado
        independe da região, então o cache é compartilhado entre cliques.
        ``total_irregulares`` = den − regular (padrão do restante).
        """
        cache_key = _make_protocolo_geral_cache_key(
            protocolo_id, user_id, status, cohortes
        )

        if not bypass_cache:
            cached = await self._get_protocolo_geral_from_cache(cache_key)
            if cached is not None:
                return cached

        async with self._client.with_user_token(user_token):
            query = self._client.table(_PROTOCOLOS_TABLE).select(
                "regular:protocolo_regular_numerador.sum(),"
                "den:protocolo_regular_denominador.sum()"
            )
            query = query.eq("protocolo_id", protocolo_id)
            if status:
                query = query.in_("pic_status", status)
            if cohortes:
                query = query.in_("pic_cohort", cohortes)
            resp = await query.execute()

        rows = resp.data or []
        resumo: RegiaoRegularidadeResumo | None = None
        if rows:
            row = rows[0]
            den = int(row.get("den") or 0)
            regular = int(row.get("regular") or 0)
            resumo = RegiaoRegularidadeResumo(
                total_participantes=den,
                total_regulares=regular,
                total_irregulares=den - regular,
                taxa_regularidade=(
                    round(regular / den * 100, 1) if den > 0 else None
                ),
            )

        # Só cacheia resultado não nulo (None não é cacheável sem sentinela;
        # protocolo sem linhas é caso raro e a consulta é de 1 linha).
        if resumo is not None:
            await self._set_protocolo_geral_cache(cache_key, resumo)
        logger.info(
            f"[geospatial] protocolo geral {protocolo_id!r}: "
            f"{'ok' if resumo else 'sem dados'} user_id={user_id!r} "
            f"status={status!r} cohortes={cohortes!r}"
        )
        return resumo

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

    # ------------------------------------------------------------------
    # Redis helpers — regularidade por camada
    # ------------------------------------------------------------------

    async def _get_regularidade_from_cache(
        self, key: str
    ) -> list[CamadaRegularidadeAggregate] | None:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(key)
            if raw is None:
                return None
            aggregates = [
                CamadaRegularidadeAggregate.model_validate(item)
                for item in json.loads(raw)
            ]
            logger.info(
                f"[geospatial] regularidade cache HIT ({len(aggregates)} rows)"
            )
            return aggregates
        except Exception as exc:
            logger.warning(f"[geospatial] regularidade cache read error (ignoring): {exc}")
            return None

    async def _set_regularidade_cache(
        self, key: str, aggregates: list[CamadaRegularidadeAggregate]
    ) -> None:
        if self._redis is None:
            return
        try:
            payload = json.dumps(
                [agg.model_dump(mode="json") for agg in aggregates]
            )
            await self._redis.set(key, payload, ex=_REGULARIDADE_CACHE_TTL)
            logger.info(
                f"[geospatial] regularidade cache SET "
                f"(TTL {_REGULARIDADE_CACHE_TTL}s)"
            )
        except Exception as exc:
            logger.warning(f"[geospatial] regularidade cache write error (ignoring): {exc}")

    # ------------------------------------------------------------------
    # Redis helpers — protocolos
    # ------------------------------------------------------------------

    async def _get_protocolos_from_cache(self, key: str) -> list[ProtocoloOption] | None:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(key)
            if raw is None:
                return None
            protocolos = [
                ProtocoloOption.model_validate(item) for item in json.loads(raw)
            ]
            logger.info(
                f"[geospatial] protocolos cache HIT ({len(protocolos)} rows)"
            )
            return protocolos
        except Exception as exc:
            logger.warning(f"[geospatial] protocolos cache read error (ignoring): {exc}")
            return None

    async def _set_protocolos_cache(
        self, key: str, protocolos: list[ProtocoloOption]
    ) -> None:
        if self._redis is None:
            return
        try:
            payload = json.dumps(
                [opt.model_dump(mode="json") for opt in protocolos]
            )
            await self._redis.set(key, payload, ex=_CACHE_TTL)
            logger.info(f"[geospatial] protocolos cache SET (TTL {_CACHE_TTL}s)")
        except Exception as exc:
            logger.warning(f"[geospatial] protocolos cache write error (ignoring): {exc}")

    # ------------------------------------------------------------------
    # Redis helpers — protocolos por região
    # ------------------------------------------------------------------

    async def _get_protocolos_regiao_from_cache(
        self, key: str
    ) -> list[RegiaoProtocoloAggregate] | None:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(key)
            if raw is None:
                return None
            protocolos = [
                RegiaoProtocoloAggregate.model_validate(item)
                for item in json.loads(raw)
            ]
            logger.info(
                f"[geospatial] protocolos por região cache HIT "
                f"({len(protocolos)} rows)"
            )
            return protocolos
        except Exception as exc:
            logger.warning(
                f"[geospatial] protocolos por região cache read error "
                f"(ignoring): {exc}"
            )
            return None

    async def _set_protocolos_regiao_cache(
        self, key: str, protocolos: list[RegiaoProtocoloAggregate]
    ) -> None:
        if self._redis is None:
            return
        try:
            payload = json.dumps(
                [agg.model_dump(mode="json") for agg in protocolos]
            )
            await self._redis.set(key, payload, ex=_REGULARIDADE_CACHE_TTL)
            logger.info(
                f"[geospatial] protocolos por região cache SET "
                f"(TTL {_REGULARIDADE_CACHE_TTL}s)"
            )
        except Exception as exc:
            logger.warning(
                f"[geospatial] protocolos por região cache write error "
                f"(ignoring): {exc}"
            )

    # ------------------------------------------------------------------
    # Redis helpers — média geral do protocolo
    # ------------------------------------------------------------------

    async def _get_protocolo_geral_from_cache(
        self, key: str
    ) -> RegiaoRegularidadeResumo | None:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(key)
            if raw is None:
                return None
            resumo = RegiaoRegularidadeResumo.model_validate(json.loads(raw))
            logger.info("[geospatial] protocolo geral cache HIT")
            return resumo
        except Exception as exc:
            logger.warning(
                f"[geospatial] protocolo geral cache read error (ignoring): {exc}"
            )
            return None

    async def _set_protocolo_geral_cache(
        self, key: str, resumo: RegiaoRegularidadeResumo
    ) -> None:
        if self._redis is None:
            return
        try:
            payload = json.dumps(resumo.model_dump(mode="json"))
            await self._redis.set(key, payload, ex=_REGULARIDADE_CACHE_TTL)
            logger.info(
                f"[geospatial] protocolo geral cache SET "
                f"(TTL {_REGULARIDADE_CACHE_TTL}s)"
            )
        except Exception as exc:
            logger.warning(
                f"[geospatial] protocolo geral cache write error (ignoring): {exc}"
            )
