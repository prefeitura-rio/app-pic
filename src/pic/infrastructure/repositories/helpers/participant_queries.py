"""Query builders for the participant PostgREST reads.

Plain builder construction (no I/O): each function receives the PostgREST
client and returns a ready-to-execute `AsyncSelectRequestBuilder`. All three
apply the same filter chain — scalar filters, free-text search, protocol
filters, secretaria restriction, situacao — over
`endpoint_participante_protocolos_wide`.
"""

from typing import Any

from postgrest import AsyncSelectRequestBuilder

from src.pic.infrastructure.postgrest_client.client import PostgrestClient
from src.pic.infrastructure.repositories.helpers.participant_columns import (
    TABLE_PROTOCOLOS_WIDE,
)
from src.pic.infrastructure.repositories.helpers.participant_filtering import (
    apply_scalar_filter,
    apply_wide_protocolo_filters,
    search_or_term,
)


def build_list_query(
    client: PostgrestClient,
    *,
    select_columns: list[str],
    column_filters: dict[str, list[Any]],
    search_term: str | None,
    protocolo_filters: dict[str, list[str]],
    secretaria_or_terms: str | None,
    situacao_values: list[Any] | None,
    sort_column: str,
    sort_descending: bool,
    count: str | None = None,
) -> AsyncSelectRequestBuilder:
    # One row per participant on the wide table, so the Content-Range
    # count reflects people (no GROUP BY anywhere).
    query = client.table(TABLE_PROTOCOLOS_WIDE).select(
        ",".join(select_columns), count=count
    )
    for column, values in column_filters.items():
        query = apply_scalar_filter(query, column, values)
    if search_term:
        query = query.or_(search_or_term(search_term))
    query = apply_wide_protocolo_filters(query, protocolo_filters)
    if secretaria_or_terms:
        query = query.or_(secretaria_or_terms)
    if situacao_values:
        query = apply_scalar_filter(query, "situacao", situacao_values)
    query = query.order(sort_column, desc=sort_descending, nullsfirst=False)
    query = query.order("id_membro_familia", desc=False, nullsfirst=False)
    return query


def build_vocab_query(
    client: PostgrestClient,
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
    query = client.table(TABLE_PROTOCOLOS_WIDE).select(",".join(columns) + ",count()")
    for column, values in scalar_filters.items():
        if column == exclude_column:
            continue
        query = apply_scalar_filter(query, column, values)
    protocolo_cascade = {
        field: values
        for field, values in protocolo_filters.items()
        if field != exclude_protocolo_field
    }
    query = apply_wide_protocolo_filters(query, protocolo_cascade)
    if secretaria_or_terms:
        query = query.or_(secretaria_or_terms)
    if search_term:
        query = query.or_(search_or_term(search_term))
    return query.order(columns[0], desc=False, nullsfirst=False)


def build_wide_aggregate_query(
    client: PostgrestClient,
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
    `wide_secretarias` (per-secretaria counter maxima); no GROUP BY columns,
    so no `count()`/`order` is added.

    Each aggregate is aliased with its own column (`col:col.count()`):
    PostgREST keys every aggregate result by the function name, so several
    unaliased `count()`/`max()` would collapse into duplicate JSON keys and
    lose all but the last value.
    """
    query = client.table(TABLE_PROTOCOLOS_WIDE).select(",".join(select_columns))
    for column, values in scalar_filters.items():
        query = apply_scalar_filter(query, column, values)
    protocolo_cascade = {
        field: values
        for field, values in protocolo_filters.items()
        if field != exclude_protocolo_field
    }
    query = apply_wide_protocolo_filters(query, protocolo_cascade)
    if secretaria_or_terms:
        query = query.or_(secretaria_or_terms)
    if search_term:
        query = query.or_(search_or_term(search_term))
    return query
