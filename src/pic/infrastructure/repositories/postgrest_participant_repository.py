"""PostgREST implementation of the participant read repository.

Replaces the BigQuery/Polars pipeline for the two migrated operations
(`GET /v2/participants`, `GET /v2/participants/{id_membro_familia}`). No
Polars anywhere in this module or its helpers.

This module is the thin orchestration layer (cache, pagination, profiling,
secretaria governance) over:

- `src.pic.infrastructure.postgrest_client.pagination` — page/limit loops and
  windowed concurrent fetches over the `PGRST_DB_MAX_ROWS` cap;
- `src.pic.infrastructure.repositories.participant_cache` — best-effort Redis
  cache facade;
- `src.pic.infrastructure.repositories.helpers` — participant_columns (tables,
  select lists, TTLs), participant_filtering (filter/sort/access builders),
  participant_queries (query builders), participant_cache_keys (deterministic
  keys), participant_governance (per-secretaria view recomputation),
  filter_vocabulary / participant_query_mapping (option vocabulary and column
  mapping).

Every read sources from `endpoint_participante_protocolos_wide` (one row per
participant); filters, sorting, pagination and `Prefer: count=exact` are
pushed to PostgREST in a single request, and the secretaria dimension is
applied in pure Python over the fetched rows. Results are cached in Redis for
1800s (short TTL for empty results); download mode (page_size=-1) skips the
cache.
"""

import json
import time
from collections.abc import AsyncIterator
from math import ceil
from typing import Any

from postgrest import AsyncSelectRequestBuilder

from src.pic.application.ports.participant_repository import ParticipantRepository
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
from src.pic.infrastructure.postgrest_client.pagination import (
    execute_query,
    fetch_next_window,
    fetch_pages,
)
from src.pic.infrastructure.repositories.helpers import (
    participant_governance as governance,
)
from src.pic.infrastructure.repositories.helpers.filter_vocabulary import (
    FILTER_OPTION_CONFIGS,
    SECRETARIA_ORDER,
    build_options,
)
from src.pic.infrastructure.repositories.helpers.participant_cache_keys import (
    make_cache_key,
    make_vocab_cache_key,
)
from src.pic.infrastructure.repositories.helpers.participant_columns import (
    CACHE_TTL_SECONDS,
    DB_MAX_ROWS,
    EMPTY_CACHE_TTL_SECONDS,
    EXPORT_FALLBACK_COLUMNS,
    EXPORT_PREFETCH_WINDOW,
    TABLE_PROTOCOLO_DETALHES,
    TABLE_PROTOCOLOS,
    TABLE_PROTOCOLOS_WIDE,
)
from src.pic.infrastructure.repositories.helpers.participant_filtering import (
    export_hidden_columns,
    list_select_columns,
    resolve_sort_column,
    secretaria_access_terms,
    split_filters,
    validate_protocol_filter_access,
)
from src.pic.infrastructure.repositories.helpers.participant_queries import (
    build_list_query,
    build_vocab_query,
    build_wide_aggregate_query,
)
from src.pic.infrastructure.repositories.helpers.participant_query_mapping import (
    FILTER_COLUMN_MAP,
    PROTOCOLO_FILTER_FIELDS,
    PROTOCOLO_STATUS_COLUMNS,
)
from src.pic.infrastructure.repositories.participant_cache import ParticipantCache
from src.utils.constants import SECRETARIA_COLUMN_PREFIX
from src.utils.data_manager_config import DataManagerConfig as config
from src.utils.data_manager_config import ProfilingData
from src.utils.log import logger


class PostgrestParticipantRepository(ParticipantRepository):
    """Participant list/detail reads straight from the data-proxy PostgREST."""

    def __init__(self, client: PostgrestClient, redis_client: Any = None) -> None:
        self._client = client
        self._cache = ParticipantCache(redis_client)

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

        search_term, situacao_values, protocolo_filters, column_filters = split_filters(
            filters
        )

        profiling.filters_applied = (
            len(column_filters) + (1 if situacao_values else 0) + len(protocolo_filters)
        )

        secretarias_acesso, full_access = governance.resolve_access(permissions)
        user_id = permissions.cpf if permissions is not None else None

        allowed_secretarias = None if full_access else set(secretarias_acesso)

        # Always validate forced protocol filters before any cache read.
        validate_protocol_filter_access(protocolo_filters, allowed_secretarias)

        sort_by = sort.sort_by
        sort_descending = sort.sort_order == "desc"
        sort_column = resolve_sort_column(sort_by, full_access, allowed_secretarias)

        page = pagination.page
        page_size = pagination.page_size  # -1 = download mode (no pagination)

        # Partial access restricts the query to the accessible secretarias
        # (`or=(<prefix>_protocolos_total.gt.0,...)`); a user with no
        # secretaria can never match protocol filters.
        secretaria_or_terms, no_protocolo_match = secretaria_access_terms(
            allowed_secretarias, bool(protocolo_filters)
        )

        # 1. Try cache (skip for download mode) ------------------------------
        use_cache = self._cache.enabled and page_size != -1
        cache_key = (
            make_cache_key(filters, pagination, sort, user_id) if use_cache else None
        )
        if cache_key and not bypass_cache:
            cached = await self._cache.get_list(cache_key)
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
                # Empty result: short TTL (see EMPTY_CACHE_TTL_SECONDS).
                await self._cache.set_list(
                    cache_key, [], meta, ttl=EMPTY_CACHE_TTL_SECONDS
                )
            return [], meta

        select_columns = list_select_columns(full_access, secretarias_acesso, sort_by)

        # Single query, filters/sort/pagination pushed to PostgREST on the
        # wide table (one row per participant, so the Content-Range count
        # equals people). Partial access recomputes the per-secretaria view
        # in-app over the fetched rows (the secretaria restriction guarantees
        # every participant has at least one accessible protocol).
        async with self._client.with_user_token(user_token):
            fetch_start = time.perf_counter()
            limit = None if page_size == -1 else page_size
            rows, total_rows = await fetch_pages(
                self._client,
                lambda count=None: build_list_query(
                    self._client,
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
                batch_size=DB_MAX_ROWS,
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
            # Empty result: short TTL — a zero-row list may be the symptom of
            # a RLS/policy-sync race on the data-proxy, and caching it for the
            # full session would keep the list wrongly empty for 30 minutes.
            ttl = (
                CACHE_TTL_SECONDS
                if data or (meta.total_rows or 0) > 0
                else EMPTY_CACHE_TTL_SECONDS
            )
            await self._cache.set_list(cache_key, data, meta, ttl=ttl)

        if not data:
            logger.warning(
                f"[participants] empty list returned: cpf={user_id} "
                f"page={page} total_rows={total_rows} "
                f"bypass_cache={bypass_cache} full_access={full_access}"
            )

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
        secretarias_acesso, full_access = governance.resolve_access(permissions)

        async with self._client.with_user_token(user_token):
            wide_result = await execute_query(
                self._client,
                self._client.table(TABLE_PROTOCOLOS_WIDE)
                .select("*")
                .filter("id_membro_familia", "eq", str(id_membro_familia))
                .limit(1),
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

                protocolos_rows, _ = await fetch_pages(
                    self._client,
                    lambda count=None: build_protocolos_query(),
                    limit=None,
                    with_count=False,
                )

            row = governance.compute_detail_view(
                participant_row,
                [
                    row_to_protocolo_item(dict(protocolo))
                    for protocolo in protocolos_rows
                ],
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
                motivos_rows, _ = await fetch_pages(
                    self._client,
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
    # CSV export (wide rows, one page per iteration)
    # ------------------------------------------------------------------

    async def export_wide_rows(
        self,
        filters: FilterCriteria,
        sort: SortParams,
        permissions: Any = None,
        user_token: str | None = None,
    ) -> AsyncIterator[list[dict[str, Any]]]:
        """Yield pages of `endpoint_participante_protocolos_wide` rows for the
        CSV export (download mode: `select("*")`, no cache).

        Same query semantics as `list_participants` — filters/sort pushed to
        PostgREST, forced protocol filters validated (403/422), partial
        access restricted to the accessible secretarias via
        `or=(<prefix>_protocolos_total.gt.0,...)`. Columns outside the
        user's reach are stripped before each page is yielded
        (`export_hidden_columns`): the CSV never contains data the user
        cannot see, and the row set/order match the list pipeline.
        """
        search_term, situacao_values, protocolo_filters, column_filters = split_filters(
            filters
        )

        secretarias_acesso, full_access = governance.resolve_access(permissions)
        allowed_secretarias = None if full_access else set(secretarias_acesso)

        validate_protocol_filter_access(protocolo_filters, allowed_secretarias)

        sort_column = resolve_sort_column(
            sort.sort_by, full_access, allowed_secretarias
        )
        sort_descending = sort.sort_order == "desc"

        secretaria_or_terms, no_protocolo_match = secretaria_access_terms(
            allowed_secretarias, bool(protocolo_filters)
        )

        if no_protocolo_match:
            return

        hidden = export_hidden_columns(
            full_access,
            secretarias_acesso,
            include_coordinates=(
                permissions is not None and permissions.is_super_admin
            ),
        )

        def build_query() -> AsyncSelectRequestBuilder:
            return build_list_query(
                self._client,
                select_columns=["*"],
                column_filters=column_filters,
                search_term=search_term,
                protocolo_filters=protocolo_filters,
                secretaria_or_terms=secretaria_or_terms,
                situacao_values=situacao_values,
                sort_column=sort_column,
                sort_descending=sort_descending,
            )

        # The user token context is scoped to each prefetch window (enter and
        # exit inside the same task). Holding `with_user_token` across the
        # `yield` would break when the StreamingResponse drains the generator
        # from a different asyncio task (ContextVar reset error), and a
        # client disconnect would leave the override set.
        offset = 0
        while True:
            async with self._client.with_user_token(user_token):
                pages, offset, done = await fetch_next_window(
                    self._client,
                    build_query,
                    offset,
                    page_size=DB_MAX_ROWS,
                    window=EXPORT_PREFETCH_WINDOW,
                )
            for page in pages:
                if hidden:
                    page = [
                        {key: value for key, value in row.items() if key not in hidden}
                        for row in page
                    ]
                yield page
            if done:
                break

    # ------------------------------------------------------------------
    # Filter options (all sourced from the wide table)
    # ------------------------------------------------------------------

    async def get_filter_options(
        self,
        field: str,
        filters: FilterCriteria,
        permissions: Any = None,
        user_token: str | None = None,
        bypass_cache: bool = False,
    ) -> list[FilterOption]:
        cfg = FILTER_OPTION_CONFIGS[field]

        secretarias_acesso, full_access = governance.resolve_access(permissions)
        if cfg.get("full_access_only") and not full_access:
            return []
        if cfg.get("needs_access") and not full_access and not secretarias_acesso:
            return []

        user_id = permissions.cpf if permissions is not None else None
        cache_key = (
            make_vocab_cache_key(field, filters, user_id)
            if self._cache.enabled
            else None
        )
        if cache_key and not bypass_cache:
            cached = await self._cache.get_vocab(cache_key)
            if cached is not None:
                return cached

        search_term, situacao_values, protocolo_filters, scalar_filters = split_filters(
            filters
        )
        if situacao_values:
            scalar_filters["situacao"] = situacao_values

        allowed_secretarias = (
            None if full_access or not secretarias_acesso else set(secretarias_acesso)
        )

        secretaria_or_terms, _ = secretaria_access_terms(allowed_secretarias)

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
                rows, _ = await fetch_pages(
                    self._client,
                    lambda count=None: build_wide_aggregate_query(
                        self._client,
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
                rows, _ = await fetch_pages(
                    self._client,
                    lambda count=None: build_wide_aggregate_query(
                        self._client,
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
                rows, _ = await fetch_pages(
                    self._client,
                    lambda count=None: build_vocab_query(
                        self._client,
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
            await self._cache.set_vocab(cache_key, options)

        logger.info(
            f"PostgREST filter options: field={field} ({len(options)} options, "
            f"full_access={full_access})"
        )
        return options


__all__ = [
    "EXPORT_FALLBACK_COLUMNS",
    "PostgrestParticipantRepository",
]
