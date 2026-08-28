"""PostgREST implementation of the participant read repository.

Replaces the BigQuery/Polars pipeline for the two migrated operations
(`GET /v2/participants`, `GET /v2/participants/{id_membro_familia}`). No
Polars anywhere in this module or its helpers.

Design notes:

- The list operation reads `endpoint_participante_resumo` (pre-aggregated
  per-secretaria counters/fractions). Protocol filters resolve through
  `endpoint_participante_protocolos_detalhe` (joined by `id_membro_familia`)
  into an `id_membro_familia=in.(...)` prefilter. The detail operation keeps
  reading `endpoint_participante_listagem` (it needs the `protocolo_listagem`
  jsonb and the irregularity motives).
- The data-proxy enforces unit RLS server-side when the request carries the
  end user's JWT (`with_user_token`). The *secretaria* dimension is not RLS;
  it is applied here, in pure Python: only columns of the accessible
  secretarias are selected, `total_fracao`/`total_protocolos_irregular` are
  recomputed from them, `situacao` is hidden for partial access and rows with
  no accessible protocols are dropped (v1 parity).
- `PGRST_DB_MAX_ROWS` (1000 on the data-proxy) caps every response, so any
  fetch of more than one page loops with limit/offset.
- Full access (super admin or all three secretarias) pushes filters, search,
  protocol ids, situacao, sorting and pagination to PostgREST. Partial access
  fetches all matching rows and filters/sorts/paginates in-app, matching the
  old pipeline's ordering.
- Results are cached in Redis keyed by a deterministic hash of (filters,
  pagination, sort, user cpf), TTL 1800s. Download mode (page_size=-1) skips
  the cache. `bypass_cache=True` skips reading but still writes.
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
from src.pic.domain.models.filters import FilterCriteria
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
)
from src.pic.infrastructure.postgrest_client.client import PostgrestClient
from src.pic.infrastructure.postgrest_client.errors import PostgrestError
from src.pic.infrastructure.repositories.helpers import (
    participant_governance as governance,
)
from src.pic.infrastructure.repositories.helpers.participant_query_mapping import (
    FILTER_COLUMN_MAP,
    PROTOCOLO_FILTER_FIELDS,
    SEARCH_COLUMNS,
    SORTABLE_COLUMNS,
)
from src.utils.constants import SECRETARIA_COLUMN_PREFIX
from src.utils.data_manager_config import DataManagerConfig as config
from src.utils.data_manager_config import ProfilingData
from src.utils.log import logger

TABLE_RESUMO = "endpoint_participante_resumo"
TABLE_LISTAGEM = "endpoint_participante_listagem"
TABLE_PROTOCOLOS = "endpoint_participante_protocolos_detalhe"
TABLE_PROTOCOLO_DETALHES = "protocolo_detalhes"

# PGRST_DB_MAX_ROWS of the data-proxy: every response is capped at this many
# rows, so "fetch everything" loops in pages of this size.
DB_MAX_ROWS = 1000

# Redis cache TTL in seconds (session lifetime).
_CACHE_TTL_SECONDS = 1800

_CACHE_PREFIX = "participants_v2:"

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


def _search_or_term(search_term: str) -> str:
    """PostgREST `or` filter for the free-text search (same 4 columns as before)."""
    pattern = f"%{_escape_ilike(search_term)}%"
    return ",".join(f"{column}.ilike.{pattern}" for column in SEARCH_COLUMNS)


def _list_select_columns(
    full_access: bool,
    secretarias_acesso: list[str],
    sort_by: str | None,
) -> list[str]:
    """Columns selected from `endpoint_participante_resumo` for this request."""
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
    ) -> tuple[list[dict[str, Any]], int | None]:
        """Fetch rows page by page, honoring PGRST_DB_MAX_ROWS.

        `limit=None` fetches everything (looping); otherwise stops once
        `limit` rows were collected, starting at `start_offset`. When
        `with_count` is set, the first page carries `Prefer: count=exact` and
        the returned total comes from the `Content-Range` header (count of
        the *filtered* set, before limit/offset).
        """
        batch_size = min(limit if limit and limit > 0 else DB_MAX_ROWS, DB_MAX_ROWS)
        offset = start_offset
        rows: list[dict[str, Any]] = []
        total: int | None = None

        while True:
            query = build_query(count="exact" if with_count and total is None else None)
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

    async def _fetch_protocolo_ids(
        self,
        protocolo_filters: dict[str, list[str]],
        allowed_secretarias: set[str] | None,
    ) -> list[str]:
        """Resolve protocol filters into `id_membro_familia` ids.

        Faithful port of the v1 `_filter_array_column_combined_polars`
        semantics over the detail table: single-value fields AND together on
        the same protocol row; the first multi-value field is expanded into
        one query per value (each ANDed with the single fields and any later
        multi-value fields via `in`) and the resulting id sets intersect.
        `allowed_secretarias` restricts matches to the user's secretarias
        (partial access), mirroring the governed-list matching of v1.
        """
        single: dict[str, str] = {}
        multi: list[tuple[str, list[str]]] = []
        for field, values in protocolo_filters.items():
            if len(values) == 1:
                single[field] = values[0]
            else:
                multi.append((field, values))

        def build_query() -> AsyncSelectRequestBuilder:
            query = self._client.table(TABLE_PROTOCOLOS).select("id_membro_familia")
            for field, value in single.items():
                query = query.ilike(field, _escape_ilike(value))
            if allowed_secretarias is not None:
                query = query.filter(
                    "protocolo_secretaria",
                    "in",
                    f"({','.join(sorted(allowed_secretarias))})",
                )
            return query

        async def fetch_ids(query: AsyncSelectRequestBuilder) -> set[str]:
            rows, _ = await self._fetch_pages(
                lambda count=None: query,
                limit=None,
                with_count=False,
            )
            return {
                str(row["id_membro_familia"])
                for row in rows
                if row.get("id_membro_familia")
            }

        if not multi:
            return sorted(await fetch_ids(build_query()))

        first_field, first_values = multi[0]
        id_sets: list[set[str]] = []
        for value in first_values:
            query = build_query()
            query = query.ilike(first_field, _escape_ilike(value))
            for field, values in multi[1:]:
                query = query.filter(field, "in", f"({','.join(values)})")
            id_sets.append(await fetch_ids(query))
        return sorted(set.intersection(*id_sets))

    def _build_list_query(
        self,
        *,
        select_columns: list[str],
        column_filters: dict[str, list[Any]],
        search_term: str | None,
        protocolo_ids: list[str] | None,
        situacao_values: list[Any] | None,
        sort_column: str,
        sort_descending: bool,
        count: str | None,
    ) -> AsyncSelectRequestBuilder:
        query = self._client.table(TABLE_RESUMO).select(
            ",".join(select_columns), count=count
        )
        for column, values in column_filters.items():
            query = _apply_scalar_filter(query, column, values)
        if search_term:
            query = query.or_(_search_or_term(search_term))
        if protocolo_ids is not None:
            query = query.filter(
                "id_membro_familia", "in", f"({','.join(protocolo_ids)})"
            )
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

        sort_by = sort.sort_by
        sort_descending = sort.sort_order == "desc"
        sort_column = _DEFAULT_SORT_COLUMN
        if sort_by and sort_by in SORTABLE_COLUMNS:
            if full_access:
                sort_column = SORTABLE_COLUMNS[sort_by]
            elif sort_by == "situacao":
                sort_column = _DEFAULT_SORT_COLUMN
            elif sort_by == "total_fracao":
                sort_column = "_regular_sum"
            else:
                sort_column = SORTABLE_COLUMNS[sort_by]

        page = pagination.page
        page_size = pagination.page_size  # -1 = download mode (no pagination)

        # 1. Try cache (skip for download mode) ------------------------------
        use_cache = self._redis is not None and page_size != -1
        cache_key = (
            _make_cache_key(filters, pagination, sort, user_id) if use_cache else None
        )
        if cache_key and not bypass_cache:
            cached = await self._get_from_cache(cache_key)
            if cached is not None:
                return cached

        select_columns = _list_select_columns(
            full_access, secretarias_acesso, sort_by
        )

        async with self._client.with_user_token(user_token):
            protocolo_ids: list[str] | None = None
            if protocolo_filters:
                allowed = None if full_access else set(secretarias_acesso)
                protocolo_ids = await self._fetch_protocolo_ids(
                    protocolo_filters, allowed
                )
                if not protocolo_ids:
                    # No participant matches the protocol filters.
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

            if not full_access:
                # In-app pipeline: fetch all matching rows, compute the view,
                # drop rows without accessible protocols, sort, paginate.
                fetch_start = time.perf_counter()
                rows, _ = await self._fetch_pages(
                    lambda count=None: self._build_list_query(
                        select_columns=select_columns,
                        column_filters=column_filters,
                        search_term=search_term,
                        protocolo_ids=protocolo_ids,
                        situacao_values=None,
                        sort_column=_DEFAULT_SORT_COLUMN,
                        sort_descending=False,
                        count=count,
                    ),
                    limit=None,
                    with_count=False,
                )
                profiling.get_dataset_s = round(
                    time.perf_counter() - fetch_start, config.PROFILING_DECIMAL_PLACES
                )
                profiling.rows_before_filter = len(rows)

                in_app_start = time.perf_counter()
                viewed = [
                    governance.compute_resumo_view(
                        row, full_access=False, secretarias_acesso=secretarias_acesso
                    )
                    for row in rows
                ]
                rows = [row for row in viewed if row is not None]
                rows = governance.sort_rows(rows, sort_column, sort_descending)
                profiling.apply_filters_s = round(
                    time.perf_counter() - in_app_start, config.PROFILING_DECIMAL_PLACES
                )
                profiling.rows_after_filter = len(rows)

                total_rows = len(rows)
                if page_size == -1:
                    result_rows = rows
                else:
                    start_idx = (page - 1) * page_size
                    result_rows = rows[start_idx : start_idx + page_size]
                profiling.paginate_s = round(
                    time.perf_counter() - in_app_start - profiling.apply_filters_s,
                    config.PROFILING_DECIMAL_PLACES,
                )
            else:
                # Pushdown pipeline: filters, search, protocol ids, situacao,
                # sort and pagination all resolved by PostgREST.
                fetch_start = time.perf_counter()
                limit = None if page_size == -1 else page_size
                rows, total_rows = await self._fetch_pages(
                    lambda count=None: self._build_list_query(
                        select_columns=select_columns,
                        column_filters=column_filters,
                        search_term=search_term,
                        protocolo_ids=protocolo_ids,
                        situacao_values=situacao_values,
                        sort_column=sort_column,
                        sort_descending=sort_descending,
                        count=count,
                    ),
                    limit=limit,
                    with_count=True,
                    start_offset=0 if page_size == -1 else (page - 1) * page_size,
                )
                profiling.get_dataset_s = round(
                    time.perf_counter() - fetch_start, config.PROFILING_DECIMAL_PLACES
                )
                if total_rows is None:
                    total_rows = len(rows)
                profiling.rows_before_filter = total_rows
                profiling.rows_after_filter = total_rows
                profiling.paginate_s = 0.0
                result_rows = rows

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
            f"PostgREST participants list: {total_rows} rows "
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
        needs_governance = bool(
            permissions is not None
            and not permissions.has_full_access()
            and not governance.has_full_protocol_access(secretarias_acesso)
        )

        async with self._client.with_user_token(user_token):
            query = (
                self._client.table(TABLE_LISTAGEM)
                .select("*")
                .filter("id_membro_familia", "eq", str(id_membro_familia))
                .limit(1)
            )
            result = await self._execute(query)
            if not result.data:
                return None

            row = dict(result.data[0])
            if needs_governance:
                row = governance.apply_secretaria_governance(row, secretarias_acesso)
                if row is None:
                    return None

            participante = row_to_participante(row)

            cpf = participante.cpf
            irregular_ids = [
                protocolo.id
                for protocolo in (participante.protocolo_listagem or [])
                if protocolo.irregular_indicador and protocolo.id
            ]
            if cpf and irregular_ids:
                motivos_rows, _ = await self._fetch_pages(
                    lambda count=None: (
                        self._client.table(TABLE_PROTOCOLO_DETALHES)
                        .select("*", count=count)
                        .filter("cpf", "eq", str(cpf))
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
