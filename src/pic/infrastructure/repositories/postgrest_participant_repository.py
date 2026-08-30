"""PostgREST implementation of the participant read repository.

Replaces the BigQuery/Polars pipeline for the two migrated operations
(`GET /v2/participants`, `GET /v2/participants/{id_membro_familia}`). No
Polars anywhere in this module or its helpers.

Design notes:

- Every read (list, filter options, detail participant row) sources from
  `endpoint_participante_protocolos_wide` (one row per participant, one
  status column per protocol — NULL when the participant lacks it). Protocol
  filters become plain column filters on that table: selected protocols are
  ANDed (`col.not.is.null`, or `col.eq/in.<status>` when protocol statuses
  are selected — every selected protocol must carry one of them); status
  alone matches any protocol (`or=` across the protocol columns); secretaria
  matches the pre-aggregated counters (`or=(<prefix>_protocolos_total.gt.0,
  ...)`, union across selected secretarias). Filters (participant, free-text
  search, protocol, situacao), sorting, pagination and `Prefer:
  count=exact` are pushed to PostgREST in a single request (one row per
  participant, so the Content-Range total counts people; `exact` because the
  wide relation is a view without relation statistics — the estimated
  planner fallback is unreliable there). Partial access restricts the query
  to the accessible secretarias via `or=(<prefix>_protocolos_total.gt.0,...)`
  and recomputes the per-secretaria view in-app over the fetched rows. The
  detail operation reads the participant row from the wide table, the
  `protocolo_listagem` items from `endpoint_participante_protocolos_detalhe`
  (counters recomputed from them), and the irregularity motives from
  `protocolo_detalhes` — all joined by `id_membro_familia`.
- Sorting by "Total" (`total_fracao`) uses the irregularidade count
  (`total_protocolos_irregular`, fewer = better first), a single column that
  PostgREST can order directly. For partial access the equivalent column is
  `<secretaria>_protocolos_irregular` (one secretaria) or the global
  `total_protocolos_irregular` (two or more).
- The data-proxy enforces unit RLS server-side when the request carries the
  end user's JWT (`with_user_token`). The *secretaria* dimension is not RLS;
  it is applied here, in pure Python: only columns of the accessible
  secretarias are selected, `total_fracao`/`total_protocolos_irregular` are
  recomputed from them, `situacao` is hidden for partial access and rows with
  no accessible protocols are dropped (v1 parity).
- `PGRST_DB_MAX_ROWS` (1000 on the data-proxy) caps every response, so any
  fetch of more than one page loops with limit/offset (download mode and
  GROUP BY pages).
- Results are cached in Redis keyed by a deterministic hash of (filters,
  pagination, sort, user cpf), TTL 1800s. Download mode (page_size=-1) skips
  the cache. `bypass_cache=True` skips reading but still writes.
- The filter options all read `endpoint_participante_protocolos_wide`:
  participant fields use one aggregate query (`select=<cols>,count()` =
  GROUP BY) per field; `protocolo_descricoes` uses a single-row
  `select=<col>:<col>.count()` per protocol column; `protocolo_secretarias`
  uses a single-row `select=<prefix>_protocolos_total:<prefix>_protocolos_total.max()`
  (each aggregate aliased with its own column so PostgREST does not collapse
  the duplicate function-name JSON keys); `protocolo_status_list`
  is a fixed backend list (helpers/filter_vocabulary.py). RLS is enforced
  server-side by the user token; the secretaria dimension is applied as
  `or=(<prefix>_protocolos_total.gt.0,...)`; the cascade (all active filters
  except the field's own) plus the free-text search are applied per query in
  pure Python (see `helpers/filter_vocabulary.py`). Options are cached in
  Redis keyed by (field, filters, user cpf).
"""

import hashlib
import json
import time
from collections.abc import Callable
from math import ceil
from typing import Any

import httpx
from postgrest import APIResponse, AsyncSelectRequestBuilder
from postgrest.exceptions import APIError

from src.pic.application.ports.participant_read_repository import ParticipantRepository
from src.pic.domain.errors import ForbiddenError, ValidationError
from src.pic.domain.models.filters import FilterCriteria, FilterOption
from src.pic.domain.models.pagination import (
    PaginationMeta,
    PaginationParams,
    SortParams,
)
from src.pic.domain.models.participante import Participante, ParticipanteListItem
from src.pic.domain.models.protocolo import ProtocoloMotivo
from src.pic.infrastructure.mappers.participant_mapper import (
    row_to_list_item,
    row_to_participante,
    row_to_protocolo_item,
)
from src.pic.infrastructure.postgrest_client.client import PostgrestClient
from src.pic.infrastructure.postgrest_client.errors import PostgrestError
from src.pic.infrastructure.repositories.helpers import (
    participant_governance as governance,
)
from src.pic.infrastructure.repositories.helpers.filter_vocabulary import (
    FILTER_OPTION_CONFIGS,
    SECRETARIA_ORDER,
    build_options,
)
from src.pic.infrastructure.repositories.helpers.participant_query_mapping import (
    FILTER_COLUMN_MAP,
    PROTOCOLO_FILTER_FIELDS,
    PROTOCOLO_SECRETARIA,
    PROTOCOLO_STATUS_COLUMNS,
    SEARCH_COLUMNS,
    SORTABLE_COLUMNS,
)
from src.utils.constants import SECRETARIA_COLUMN_PREFIX
from src.utils.data_manager_config import DataManagerConfig as config
from src.utils.data_manager_config import ProfilingData
from src.utils.log import logger

TABLE_PROTOCOLOS = "endpoint_participante_protocolos_detalhe"
TABLE_PROTOCOLO_DETALHES = "protocolo_detalhes"
TABLE_PROTOCOLOS_WIDE = "endpoint_participante_protocolos_wide"

# PGRST_DB_MAX_ROWS of the data-proxy: every response is capped at this many
# rows, so "fetch everything" loops in pages of this size.
DB_MAX_ROWS = 1000

# Redis cache TTL in seconds (session lifetime).
_CACHE_TTL_SECONDS = 1800

_CACHE_PREFIX = "participants_v2:"

_VOCAB_CACHE_PREFIX = "filters_v2:"

_DEFAULT_SORT_COLUMN = "nome"

# Columns filtered with exact equality instead of ILIKE: unit IDs may be
# numeric in Postgres (ILIKE needs text), and dates have no casing.
_EXACT_COLUMNS = {
    "id_cre",
    "id_ap",
    "id_cas",
    "id_cras",
    "id_escola",
    "id_clinica_familia",
    "id_equipe_familia",
    "cohort",
}

# Columns every list view selects.
_BASE_LIST_COLUMNS = [
    "id_familia",
    "id_membro_familia",
    "nome",
    "cpf",
    "grupo",
    "bairro",
    "idade",
    "status",
    "raca",
]

# Full-access extras returned verbatim from the resumo table.
_FULL_ACCESS_COLUMNS = [
    "situacao",
    "total_fracao",
    "assistencia_fracao",
    "educacao_fracao",
    "saude_fracao",
    "total_protocolos_irregular",
]


def _escape_ilike(value: str) -> str:
    """Escape ILIKE wildcards so the value matches literally."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _split_values(value: Any) -> list[Any]:
    """Split pipe-separated multi-select filter values (frontend convention)."""
    if isinstance(value, str) and "|" in value:
        return [v.strip() for v in value.split("|") if v.strip()]
    return [value]


def _clean_values(values: list[Any]) -> list[Any]:
    """Drop "todos"/"todas"/empty values, keeping booleans (mirrors DataManager)."""
    cleaned: list[Any] = []
    for value in values:
        if isinstance(value, bool):
            cleaned.append(value)
        elif (
            value
            and str(value).strip()
            and str(value) not in config.FILTER_IGNORE_VALUES
        ):
            cleaned.append(value)
    return cleaned


def _apply_scalar_filter(
    query: AsyncSelectRequestBuilder, column: str, values: list[Any]
) -> AsyncSelectRequestBuilder:
    """Add one (possibly multi-value) scalar filter.

    Text columns use ILIKE equality (case-insensitive, like the old pipeline
    that lowercased everything); unit-ID/date columns use exact equality.
    """
    if column == "has_bolsa_familia":
        bool_values = ["true" if isinstance(v, bool) and v else "false" for v in values]
        if len(bool_values) > 1:
            return query.or_(",".join(f"{column}.is.{v}" for v in bool_values))
        return query.filter(column, "is", bool_values[0])

    if column in _EXACT_COLUMNS:
        if len(values) > 1:
            return query.filter(
                column,
                "in",
                f"({','.join(str(v) for v in values)})",
            )
        return query.eq(column, str(values[0]))

    if len(values) > 1:
        return query.filter(
            column,
            "in",
            f"({','.join(str(v) for v in values)})",
        )
    return query.ilike(column, _escape_ilike(str(values[0])))


def _apply_wide_protocolo_filters(
    query: AsyncSelectRequestBuilder,
    protocolo_filters: dict[str, list[str]],
) -> AsyncSelectRequestBuilder:
    """Protocol filters on `endpoint_participante_protocolos_wide`.

    The wide table has one row per participant and one status column per
    protocol (column name == protocolo_id, NULL without the protocol):

    - `protocolo_id` (descricao) values select whole protocol columns; the
      participant must have every selected protocol (AND, one filter per
      column: `col.not.is.null`, or `col.eq/in.<status>` when protocol
      statuses are also selected — each selected protocol must carry one of
      them).
    - `protocolo_status_label` alone matches any protocol with one of the
      selected statuses (`or=` across every protocol column).
    - `protocolo_secretaria` matches the pre-aggregated counters
      (`or=(<prefix>_protocolos_total.gt.0,...)`, union across selected
      secretarias).
    """
    descricao_ids = protocolo_filters.get("protocolo_id") or []
    status_values = protocolo_filters.get("protocolo_status_label") or []
    secretaria_values = protocolo_filters.get("protocolo_secretaria") or []

    for protocolo_id in descricao_ids:
        if status_values:
            if len(status_values) == 1:
                query = query.eq(protocolo_id, status_values[0])
            else:
                query = query.in_(protocolo_id, status_values)
        else:
            query = query.not_.is_(protocolo_id, "null")

    if not descricao_ids and status_values:
        terms = [
            f"{column}.eq.{status}"
            for status in status_values
            for column in PROTOCOLO_STATUS_COLUMNS
        ]
        query = query.or_(",".join(terms))

    if secretaria_values:
        terms = [
            f"{SECRETARIA_COLUMN_PREFIX[secretaria]}_protocolos_total.gt.0"
            for secretaria in secretaria_values
            if secretaria in SECRETARIA_COLUMN_PREFIX
        ]
        if terms:
            query = query.or_(",".join(terms))
    return query


def _search_or_term(search_term: str) -> str:
    """PostgREST `or` filter for the free-text search (same 4 columns as before)."""
    pattern = f"%{_escape_ilike(search_term)}%"
    return ",".join(f"{column}.ilike.{pattern}" for column in SEARCH_COLUMNS)


def _validate_protocol_filter_access(
    protocolo_filters: dict[str, list[str]],
    allowed_secretarias: set[str] | None,
) -> None:
    """Reject forced protocol filters outside the user's reach.

    Unknown protocol ids / secretaria values are bad requests (422); known
    values belonging to secretarias the user cannot access are forbidden
    (403). `allowed_secretarias=None` means full access: only the unknown
    value validation applies.
    """
    for protocolo_id in protocolo_filters.get("protocolo_id") or []:
        secretaria = PROTOCOLO_SECRETARIA.get(protocolo_id)
        if secretaria is None:
            raise ValidationError(f"Protocolo desconhecido: {protocolo_id}")
        if (
            allowed_secretarias is not None
            and secretaria not in allowed_secretarias
        ):
            raise ForbiddenError(
                f"Sem acesso a protocolos da secretaria {secretaria}"
            )
    for secretaria in protocolo_filters.get("protocolo_secretaria") or []:
        if secretaria not in SECRETARIA_COLUMN_PREFIX:
            raise ValidationError(f"Secretaria desconhecida: {secretaria}")
        if (
            allowed_secretarias is not None
            and secretaria not in allowed_secretarias
        ):
            raise ForbiddenError(
                f"Sem acesso a protocolos da secretaria {secretaria}"
            )


def _list_select_columns(
    full_access: bool,
    secretarias_acesso: list[str],
    sort_by: str | None,
) -> list[str]:
    """Columns selected from `endpoint_participante_protocolos_wide`
    (participant columns plus the per-secretaria counters)."""
    columns = list(_BASE_LIST_COLUMNS)
    if full_access:
        columns.extend(_FULL_ACCESS_COLUMNS)
        sort_column = SORTABLE_COLUMNS.get(sort_by or "", _DEFAULT_SORT_COLUMN)
        if sort_column not in columns:
            columns.append(sort_column)
    else:
        allowed = set(secretarias_acesso)
        for secretaria, prefix in SECRETARIA_COLUMN_PREFIX.items():
            if secretaria not in allowed:
                continue
            columns.extend(
                [
                    f"{prefix}_fracao",
                    f"{prefix}_protocolos_total",
                    f"{prefix}_protocolos_regular",
                    f"{prefix}_protocolos_irregular",
                ]
            )
    return columns


def _make_cache_key(
    filters: FilterCriteria,
    pagination: PaginationParams,
    sort: SortParams,
    user_id: str | None,
) -> str:
    """Deterministic cache key isolating each user (cpf) and request shape."""
    payload = json.dumps(
        {
            "filters": filters.model_dump(exclude_none=True),
            "page": pagination.page,
            "page_size": pagination.page_size,
            "sort_by": sort.sort_by,
            "sort_order": sort.sort_order,
            "user_id": user_id,
        },
        sort_keys=True,
        default=str,
    )
    return _CACHE_PREFIX + hashlib.sha256(payload.encode()).hexdigest()


def _make_vocab_cache_key(
    field: str, filters: FilterCriteria, user_id: str | None
) -> str:
    """Deterministic cache key for one filter field's options (per user cpf)."""
    payload = json.dumps(
        {
            "field": field,
            "filters": filters.model_dump(exclude_none=True),
            "user_id": user_id,
        },
        sort_keys=True,
        default=str,
    )
    return _VOCAB_CACHE_PREFIX + hashlib.sha256(payload.encode()).hexdigest()


class PostgrestParticipantRepository(ParticipantRepository):
    """Participant list/detail reads straight from the data-proxy PostgREST."""

    def __init__(self, client: PostgrestClient, redis_client: Any = None) -> None:
        self._client = client
        self._redis = redis_client

    async def _execute(self, query: AsyncSelectRequestBuilder) -> APIResponse:
        try:
            return await query.execute()
        except APIError as error:
            raise PostgrestError.from_api_error(error) from error
        except httpx.HTTPError as error:
            raise PostgrestError.from_transport_error(error) from error

    async def _fetch_pages(
        self,
        build_query: Callable[..., AsyncSelectRequestBuilder],
        *,
        limit: int | None,
        with_count: bool,
        start_offset: int = 0,
        count_method: str = "estimated",
    ) -> tuple[list[dict[str, Any]], int | None]:
        """Fetch rows page by page, honoring PGRST_DB_MAX_ROWS.

        `limit=None` fetches everything (looping); otherwise stops once
        `limit` rows were collected, starting at `start_offset`. When
        `with_count` is set, the first page carries `Prefer: count=<method>`
        and the returned total comes from the `Content-Range` header (count
        of the *filtered* set, before limit/offset). `count_method` picks
        the PostgREST count mode: `exact` for views (no relation statistics
        for the `estimated` planner fallback) and `estimated` for plain
        tables.

        Contract: `build_query` MUST return a fresh query builder on every
        call. The postgrest-py builders are mutable (offset/limit/filters
        accumulate on the same instance), so reusing a captured builder
        across pages appends duplicate query params to each request.
        """
        batch_size = min(limit if limit and limit > 0 else DB_MAX_ROWS, DB_MAX_ROWS)
        offset = start_offset
        rows: list[dict[str, Any]] = []
        total: int | None = None

        while True:
            query = build_query(
                count=count_method if with_count and total is None else None
            )
            page_limit = (
                min(batch_size, limit - len(rows))
                if limit and limit > 0
                else batch_size
            )
            result = await self._execute(query.offset(offset).limit(page_limit))
            page = list(result.data)
            if with_count and total is None:
                total = result.count

            rows.extend(page)
            offset += len(page)

            if limit and limit > 0 and len(rows) >= limit:
                break
            if len(page) < page_limit:
                break

        return rows, total

    def _build_list_query(
        self,
        *,
        select_columns: list[str],
        column_filters: dict[str, list[Any]],
        search_term: str | None,
        protocolo_filters: dict[str, list[str]],
        secretaria_or_terms: str | None,
        situacao_values: list[Any] | None,
        sort_column: str,
        sort_descending: bool,
        count: str | None,
    ) -> AsyncSelectRequestBuilder:
        # One row per participant on the wide table, so the Content-Range
        # count reflects people (no GROUP BY anywhere).
        query = self._client.table(TABLE_PROTOCOLOS_WIDE).select(
            ",".join(select_columns), count=count
        )
        for column, values in column_filters.items():
            query = _apply_scalar_filter(query, column, values)
        if search_term:
            query = query.or_(_search_or_term(search_term))
        query = _apply_wide_protocolo_filters(query, protocolo_filters)
        if secretaria_or_terms:
            query = query.or_(secretaria_or_terms)
        if situacao_values:
            query = _apply_scalar_filter(query, "situacao", situacao_values)
        query = query.order(sort_column, desc=sort_descending, nullsfirst=False)
        query = query.order("id_membro_familia", desc=False, nullsfirst=False)
        return query

    # ------------------------------------------------------------------
    # Redis cache helpers
    # ------------------------------------------------------------------

    async def _get_from_cache(
        self, key: str
    ) -> tuple[list[ParticipanteListItem], PaginationMeta] | None:
        try:
            raw = await self._redis.get(key)
            if raw is None:
                return None
            payload = json.loads(raw)
            data = [
                ParticipanteListItem.model_validate(item)
                for item in payload["data"]
            ]
            meta = PaginationMeta.model_validate(payload["meta"])
            meta.cache_hit = True
            logger.info(f"[participants] cache HIT ({len(data)} rows)")
            return data, meta
        except Exception as exc:
            logger.warning(f"[participants] cache read error (ignoring): {exc}")
            return None

    async def _set_cache(
        self,
        key: str,
        data: list[ParticipanteListItem],
        meta: PaginationMeta,
    ) -> None:
        try:
            payload = json.dumps(
                {
                    "data": [item.model_dump(mode="json") for item in data],
                    "meta": meta.model_dump(mode="json"),
                }
            )
            await self._redis.set(key, payload, ex=_CACHE_TTL_SECONDS)
            logger.info(f"[participants] cache SET ({len(data)} rows, TTL {_CACHE_TTL_SECONDS}s)")
        except Exception as exc:
            logger.warning(f"[participants] cache write error (ignoring): {exc}")

    async def _get_vocab_from_cache(self, key: str) -> list[FilterOption] | None:
        try:
            raw = await self._redis.get(key)
            if raw is None:
                return None
            logger.info("[filters] cache HIT")
            return [FilterOption.model_validate(item) for item in json.loads(raw)]
        except Exception as exc:
            logger.warning(f"[filters] cache read error (ignoring): {exc}")
            return None

    async def _set_vocab_cache(
        self, key: str, options: list[FilterOption]
    ) -> None:
        try:
            payload = json.dumps([opt.model_dump(mode="json") for opt in options])
            await self._redis.set(key, payload, ex=_CACHE_TTL_SECONDS)
            logger.info(f"[filters] cache SET (TTL {_CACHE_TTL_SECONDS}s)")
        except Exception as exc:
            logger.warning(f"[filters] cache write error (ignoring): {exc}")

    # ------------------------------------------------------------------
    # Public interface (ParticipantRepository)
    # ------------------------------------------------------------------

    async def list_participants(
        self,
        filters: FilterCriteria,
        pagination: PaginationParams,
        sort: SortParams,
        permissions: Any = None,
        user_token: str | None = None,
        bypass_cache: bool = False,
    ) -> tuple[list[ParticipanteListItem], PaginationMeta]:
        pipeline_start = time.perf_counter()
        profiling = ProfilingData()

        filters_dict = filters.model_dump(exclude_none=True)
        search_term = filters_dict.pop("search", None)

        situacao_values: list[Any] | None = None
        if "situacao" in filters_dict:
            situacao_values = _clean_values(_split_values(filters_dict.pop("situacao")))
            if not situacao_values:
                situacao_values = None

        protocolo_filters: dict[str, list[str]] = {}
        for key, field in PROTOCOLO_FILTER_FIELDS.items():
            if key in filters_dict:
                values = _clean_values(
                    [str(v) for v in _split_values(filters_dict.pop(key))]
                )
                if values:
                    protocolo_filters[field] = values

        column_filters: dict[str, list[Any]] = {}
        for key, value in filters_dict.items():
            if key in FILTER_COLUMN_MAP:
                values = _clean_values(_split_values(value))
                if values:
                    column_filters[FILTER_COLUMN_MAP[key]] = values

        profiling.filters_applied = (
            len(column_filters) + (1 if situacao_values else 0) + len(protocolo_filters)
        )

        secretarias_acesso = (
            list(permissions.secretarias_acesso)
            if permissions is not None
            else sorted(governance.ALL_SECRETARIAS)
        )
        full_access = (
            permissions is None
            or permissions.has_full_access()
            or governance.has_full_protocol_access(secretarias_acesso)
        )
        user_id = permissions.cpf if permissions is not None else None

        allowed_secretarias = None if full_access else set(secretarias_acesso)

        # Always validate forced protocol filters before any cache read.
        _validate_protocol_filter_access(protocolo_filters, allowed_secretarias)

        sort_by = sort.sort_by
        sort_descending = sort.sort_order == "desc"
        sort_column = _DEFAULT_SORT_COLUMN
        if sort_by and sort_by in SORTABLE_COLUMNS:
            if full_access:
                sort_column = SORTABLE_COLUMNS[sort_by]
            elif sort_by == "situacao":
                sort_column = _DEFAULT_SORT_COLUMN
            elif sort_by in ("total_fracao", "total_irregular"):
                # "Total" sorts by irregularidade (fewer = better first).
                if len(allowed_secretarias) == 1:
                    prefix = SECRETARIA_COLUMN_PREFIX[next(iter(allowed_secretarias))]
                    sort_column = f"{prefix}_protocolos_irregular"
                elif allowed_secretarias:
                    sort_column = "total_protocolos_irregular"
                else:
                    sort_column = _DEFAULT_SORT_COLUMN
            else:
                sort_column = SORTABLE_COLUMNS[sort_by]

        page = pagination.page
        page_size = pagination.page_size  # -1 = download mode (no pagination)

        # The wide table has one row per participant. Partial access is
        # restricted to the accessible secretarias via
        # `or=(<prefix>_protocolos_total.gt.0,...)` (ANDed with any
        # user-selected protocol filters); a user with no secretaria can
        # never match protocol filters.
        no_protocolo_match = False
        secretaria_or_terms: str | None = None
        if allowed_secretarias is not None:
            if allowed_secretarias:
                secretaria_or_terms = ",".join(
                    f"{SECRETARIA_COLUMN_PREFIX[secretaria]}_protocolos_total.gt.0"
                    for secretaria in sorted(allowed_secretarias)
                )
            elif protocolo_filters:
                no_protocolo_match = True

        # 1. Try cache (skip for download mode) ------------------------------
        use_cache = self._redis is not None and page_size != -1
        cache_key = (
            _make_cache_key(filters, pagination, sort, user_id) if use_cache else None
        )
        if cache_key and not bypass_cache:
            cached = await self._get_from_cache(cache_key)
            if cached is not None:
                return cached

        if no_protocolo_match:
            meta = PaginationMeta(
                page=page,
                page_size=page_size if page_size != -1 else None,
                total_rows=0,
                total_pages=0,
                cache_hit=False,
                profiling=profiling.to_dict(),
                can_view_dashboard=None,
            )
            if cache_key:
                await self._set_cache(cache_key, [], meta)
            return [], meta

        select_columns = _list_select_columns(
            full_access, secretarias_acesso, sort_by
        )

        # Single query, filters/sort/pagination pushed to PostgREST on the
        # wide table (one row per participant, so the Content-Range count
        # equals people). Partial access recomputes the per-secretaria view
        # in-app over the fetched rows (the secretaria restriction guarantees
        # every participant has at least one accessible protocol).
        async with self._client.with_user_token(user_token):
            fetch_start = time.perf_counter()
            limit = None if page_size == -1 else page_size
            rows, total_rows = await self._fetch_pages(
                lambda count=None: self._build_list_query(
                    select_columns=select_columns,
                    column_filters=column_filters,
                    search_term=search_term,
                    protocolo_filters=protocolo_filters,
                    secretaria_or_terms=secretaria_or_terms,
                    situacao_values=situacao_values if full_access else None,
                    sort_column=sort_column,
                    sort_descending=sort_descending,
                    count=count,
                ),
                limit=limit,
                with_count=True,
                start_offset=0 if page_size == -1 else (page - 1) * page_size,
                # The wide relation is a view (no reltuples statistics), so
                # the estimated count's planner fallback is unreliable there;
                # exact counts rows with the same WHERE and returns the real
                # number of participants.
                count_method="exact",
            )
            profiling.get_dataset_s = round(
                time.perf_counter() - fetch_start, config.PROFILING_DECIMAL_PLACES
            )
            if total_rows is None:
                total_rows = len(rows)
            profiling.rows_before_filter = total_rows

            result_rows = rows
            if not full_access:
                in_app_start = time.perf_counter()
                viewed = [
                    governance.compute_resumo_view(
                        row, full_access=False, secretarias_acesso=secretarias_acesso
                    )
                    for row in rows
                ]
                result_rows = [row for row in viewed if row is not None]
                profiling.apply_filters_s = round(
                    time.perf_counter() - in_app_start, config.PROFILING_DECIMAL_PLACES
                )
                profiling.rows_after_filter = len(result_rows)
                profiling.paginate_s = 0.0
            else:
                profiling.rows_after_filter = total_rows
                profiling.paginate_s = 0.0

        if search_term:
            profiling.rows_after_search = total_rows

        convert_start = time.perf_counter()
        data = [row_to_list_item(row) for row in result_rows]
        profiling.convert_to_dict_s = round(
            time.perf_counter() - convert_start, config.PROFILING_DECIMAL_PLACES
        )

        if page_size == -1:
            total_pages = 1
        else:
            total_pages = ceil(total_rows / page_size) if total_rows > 0 else 0

        profiling.total_pipeline_s = round(
            time.perf_counter() - pipeline_start, config.PROFILING_DECIMAL_PLACES
        )

        meta = PaginationMeta(
            page=page,
            page_size=page_size if page_size != -1 else None,
            total_rows=total_rows,
            total_pages=total_pages,
            cache_hit=False,
            profiling=profiling.to_dict(),
            can_view_dashboard=None,
        )

        if cache_key:
            await self._set_cache(cache_key, data, meta)

        logger.info(
            f"PostgREST participants list ({TABLE_PROTOCOLOS_WIDE}): "
            f"{total_rows} rows "
            f"(page={page}, page_size={page_size}, in_app={not full_access})"
        )
        return data, meta

    async def get_participant_by_id(
        self,
        id_membro_familia: str,
        permissions: Any = None,
        user_token: str | None = None,
    ) -> Participante | None:
        secretarias_acesso = (
            list(permissions.secretarias_acesso)
            if permissions is not None
            else sorted(governance.ALL_SECRETARIAS)
        )
        full_access = (
            permissions is None
            or permissions.has_full_access()
            or governance.has_full_protocol_access(secretarias_acesso)
        )

        async with self._client.with_user_token(user_token):
            wide_result = await self._execute(
                self._client.table(TABLE_PROTOCOLOS_WIDE)
                .select("*")
                .filter("id_membro_familia", "eq", str(id_membro_familia))
                .limit(1)
            )
            if not wide_result.data:
                return None

            participant_row = dict(wide_result.data[0])

            protocolos_rows: list[dict[str, Any]] = []
            if full_access or secretarias_acesso:

                def build_protocolos_query() -> AsyncSelectRequestBuilder:
                    query = (
                        self._client.table(TABLE_PROTOCOLOS)
                        .select("*")
                        .filter("id_membro_familia", "eq", str(id_membro_familia))
                    )
                    if not full_access:
                        query = query.filter(
                            "protocolo_secretaria",
                            "in",
                            f"({','.join(sorted(secretarias_acesso))})",
                        )
                    return query.order(
                        "protocolo_secretaria", desc=False, nullsfirst=False
                    ).order("protocolo_id", desc=False, nullsfirst=False)

                protocolos_rows, _ = await self._fetch_pages(
                    lambda count=None: build_protocolos_query(),
                    limit=None,
                    with_count=False,
                )

            row = governance.compute_detail_view(
                participant_row,
                [row_to_protocolo_item(dict(protocolo)) for protocolo in protocolos_rows],
                secretarias_acesso,
                full_access=full_access,
            )
            if row is None:
                return None

            participante = row_to_participante(row)

            irregular_ids = [
                protocolo.id
                for protocolo in (participante.protocolo_listagem or [])
                if protocolo.irregular_indicador and protocolo.id
            ]
            if irregular_ids:
                motivos_rows, _ = await self._fetch_pages(
                    lambda count=None: (
                        self._client.table(TABLE_PROTOCOLO_DETALHES)
                        .select("*", count=count)
                        .filter("id_membro_familia", "eq", str(id_membro_familia))
                    ),
                    limit=None,
                    with_count=False,
                )
                lookup: dict[str, Any] = {}
                for motivos_row in motivos_rows:
                    protocolo_id = motivos_row.get("protocolo_id")
                    if protocolo_id:
                        lookup[str(protocolo_id)] = motivos_row.get("protocolo_motivo")

                for protocolo in participante.protocolo_listagem or []:
                    if not protocolo.irregular_indicador or not protocolo.id:
                        continue
                    motivo_raw = lookup.get(str(protocolo.id))
                    if motivo_raw:
                        data = (
                            json.loads(motivo_raw)
                            if isinstance(motivo_raw, str)
                            else motivo_raw
                        )
                        protocolo.protocolo_motivo = ProtocoloMotivo.model_validate(
                            data
                        )

        return participante

    # ------------------------------------------------------------------
    # Filter options (all sourced from the wide table)
    # ------------------------------------------------------------------

    def _build_vocab_query(
        self,
        columns: list[str],
        *,
        scalar_filters: dict[str, list[Any]],
        protocolo_filters: dict[str, list[str]],
        exclude_column: str | None,
        exclude_protocolo_field: str | None,
        search_term: str | None,
        secretaria_or_terms: str | None,
    ) -> AsyncSelectRequestBuilder:
        """One aggregate (GROUP BY) query for a single option list.

        Applies every active filter except the field's own (cascade), the
        free-text search, and — for partial access — the secretaria
        restriction (`or=(<prefix>_protocolos_total.gt.0,...)`).
        """
        query = self._client.table(TABLE_PROTOCOLOS_WIDE).select(
            ",".join(columns) + ",count()"
        )
        for column, values in scalar_filters.items():
            if column == exclude_column:
                continue
            query = _apply_scalar_filter(query, column, values)
        protocolo_cascade = {
            field: values
            for field, values in protocolo_filters.items()
            if field != exclude_protocolo_field
        }
        query = _apply_wide_protocolo_filters(query, protocolo_cascade)
        if secretaria_or_terms:
            query = query.or_(secretaria_or_terms)
        if search_term:
            query = query.or_(_search_or_term(search_term))
        return query.order(columns[0], desc=False, nullsfirst=False)

    def _build_wide_aggregate_query(
        self,
        select_columns: list[str],
        *,
        scalar_filters: dict[str, list[Any]],
        protocolo_filters: dict[str, list[str]],
        exclude_protocolo_field: str | None,
        search_term: str | None,
        secretaria_or_terms: str | None,
    ) -> AsyncSelectRequestBuilder:
        """Single-row pure-aggregate query over the wide table.

        Used for `wide_counts` (one `col.count()` per protocol) and
        `wide_secretarias` (per-secretaria counter maxima); no GROUP BY
        columns, so no `count()`/`order` is added.

        Each aggregate is aliased with its own column (`col:col.count()`):
        PostgREST keys every aggregate result by the function name, so
        several unaliased `count()`/`max()` would collapse into duplicate
        JSON keys and lose all but the last value.
        """
        query = self._client.table(TABLE_PROTOCOLOS_WIDE).select(
            ",".join(select_columns)
        )
        for column, values in scalar_filters.items():
            query = _apply_scalar_filter(query, column, values)
        protocolo_cascade = {
            field: values
            for field, values in protocolo_filters.items()
            if field != exclude_protocolo_field
        }
        query = _apply_wide_protocolo_filters(query, protocolo_cascade)
        if secretaria_or_terms:
            query = query.or_(secretaria_or_terms)
        if search_term:
            query = query.or_(_search_or_term(search_term))
        return query

    async def get_filter_options(
        self,
        field: str,
        filters: FilterCriteria,
        permissions: Any = None,
        user_token: str | None = None,
        bypass_cache: bool = False,
    ) -> list[FilterOption]:
        cfg = FILTER_OPTION_CONFIGS[field]

        secretarias_acesso = (
            list(permissions.secretarias_acesso)
            if permissions is not None
            else sorted(governance.ALL_SECRETARIAS)
        )
        full_access = (
            permissions is None
            or permissions.has_full_access()
            or governance.has_full_protocol_access(secretarias_acesso)
        )
        if cfg.get("full_access_only") and not full_access:
            return []
        if cfg.get("needs_access") and not full_access and not secretarias_acesso:
            return []

        user_id = permissions.cpf if permissions is not None else None
        cache_key = (
            _make_vocab_cache_key(field, filters, user_id)
            if self._redis is not None
            else None
        )
        if cache_key and not bypass_cache:
            cached = await self._get_vocab_from_cache(cache_key)
            if cached is not None:
                return cached

        filters_dict = filters.model_dump(exclude_none=True)
        search_term = filters_dict.pop("search", None)

        scalar_filters: dict[str, list[Any]] = {}
        for key, value in filters_dict.items():
            if key in FILTER_COLUMN_MAP:
                values = _clean_values(_split_values(value))
                if values:
                    scalar_filters[FILTER_COLUMN_MAP[key]] = values

        protocolo_filters: dict[str, list[str]] = {}
        for key, proto_field in PROTOCOLO_FILTER_FIELDS.items():
            if key in filters_dict:
                values = _clean_values(
                    [str(v) for v in _split_values(filters_dict.pop(key))]
                )
                if values:
                    protocolo_filters[proto_field] = values

        allowed_secretarias = (
            None
            if full_access or not secretarias_acesso
            else set(secretarias_acesso)
        )

        secretaria_or_terms: str | None = None
        if allowed_secretarias:
            secretaria_or_terms = ",".join(
                f"{SECRETARIA_COLUMN_PREFIX[secretaria]}_protocolos_total.gt.0"
                for secretaria in sorted(allowed_secretarias)
            )

        kind = cfg["kind"]
        exclude_protocolo_field = PROTOCOLO_FILTER_FIELDS.get(cfg.get("filter_key"))

        allowed_for_options = allowed_secretarias
        if kind == "wide_counts":
            # Protocol options are columns, so a selected secretaria filter
            # (which only restricts rows) must also restrict which protocol
            # columns become options (intersected with partial access).
            selected_secretarias = set(
                protocolo_filters.get("protocolo_secretaria") or []
            )
            if selected_secretarias:
                allowed_for_options = (
                    selected_secretarias
                    if allowed_for_options is None
                    else allowed_for_options & selected_secretarias
                )

        async with self._client.with_user_token(user_token):
            if kind == "static_status":
                rows: list[dict[str, Any]] = []
            elif kind == "wide_counts":
                rows, _ = await self._fetch_pages(
                    lambda count=None: self._build_wide_aggregate_query(
                        [
                            f"{column}:{column}.count()"
                            for column in PROTOCOLO_STATUS_COLUMNS
                        ],
                        scalar_filters=scalar_filters,
                        protocolo_filters=protocolo_filters,
                        exclude_protocolo_field=exclude_protocolo_field,
                        search_term=search_term,
                        secretaria_or_terms=secretaria_or_terms,
                    ),
                    limit=None,
                    with_count=False,
                )
            elif kind == "wide_secretarias":
                rows, _ = await self._fetch_pages(
                    lambda count=None: self._build_wide_aggregate_query(
                        [
                            f"{SECRETARIA_COLUMN_PREFIX[secretaria]}_protocolos_total:"
                            f"{SECRETARIA_COLUMN_PREFIX[secretaria]}_protocolos_total.max()"
                            for secretaria in SECRETARIA_ORDER
                        ],
                        scalar_filters=scalar_filters,
                        protocolo_filters=protocolo_filters,
                        exclude_protocolo_field=exclude_protocolo_field,
                        search_term=search_term,
                        secretaria_or_terms=secretaria_or_terms,
                    ),
                    limit=None,
                    with_count=False,
                )
            else:
                rows, _ = await self._fetch_pages(
                    lambda count=None: self._build_vocab_query(
                        cfg["columns"],
                        scalar_filters=scalar_filters,
                        protocolo_filters=protocolo_filters,
                        exclude_column=FILTER_COLUMN_MAP.get(cfg.get("filter_key")),
                        exclude_protocolo_field=exclude_protocolo_field,
                        search_term=search_term,
                        secretaria_or_terms=secretaria_or_terms,
                    ),
                    limit=None,
                    with_count=False,
                )

        options = build_options(
            cfg,
            list(rows),
            allowed_secretarias=allowed_for_options,
        )

        if cache_key:
            await self._set_vocab_cache(cache_key, options)

        logger.info(
            f"PostgREST filter options: field={field} ({len(options)} options, "
            f"full_access={full_access})"
        )
        return options
