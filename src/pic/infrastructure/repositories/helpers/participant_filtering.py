"""Pure-Python filter/query builders for the participant PostgREST reads.

Everything here is a plain function over PostgREST query builders or filter
dicts — no I/O, no class state — with the exact v1 DataManager semantics used
by the list pipeline.

Design notes:

- Every read sources from `endpoint_participante_protocolos_wide` (one row
  per participant, one status column per protocol — NULL when the participant
  lacks it). Protocol filters become plain column filters on that table:
  selected protocols are ANDed (`col.not.is.null`, or `col.eq/in.<status>`
  when protocol statuses are also selected — every selected protocol must
  carry one of them); status alone matches any protocol (`or=` across the
  protocol columns); secretaria matches the pre-aggregated counters
  (`or=(<prefix>_protocolos_total.gt.0, ...)`, union across selected
  secretarias). Filters (participant, free-text search, protocol, situacao)
  are pushed to PostgREST in a single request.
- Sorting by "Total" (`total_fracao`) uses the irregularidade count
  (`total_protocolos_irregular`, fewer = better first), a single column that
  PostgREST can order directly. For partial access the equivalent column is
  `<secretaria>_protocolos_irregular` (one secretaria) or the global
  `total_protocolos_irregular` (two or more).
- The *secretaria* dimension is not RLS; it is applied here, in pure Python:
  only columns of the accessible secretarias are selected,
  `total_fracao`/`total_protocolos_irregular` are recomputed from them,
  `situacao` is hidden for partial access and rows with no accessible
  protocols are dropped (v1 parity).
"""

from typing import Any

from postgrest import AsyncSelectRequestBuilder

from src.pic.domain.errors import ForbiddenError, ValidationError
from src.pic.domain.models.filters import FilterCriteria
from src.pic.infrastructure.repositories.helpers.participant_columns import (
    BASE_LIST_COLUMNS,
    DEFAULT_SORT_COLUMN,
    EXACT_COLUMNS,
    EXPORT_GLOBAL_COLUMNS,
    FULL_ACCESS_COLUMNS,
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

# Request value -> PostgREST condition for the `has_cartao_pic` bool column.
CARTAO_PIC_STATUS_VALUES = {
    "retirado": "true",
    "nao_retirou": "false",
    "sem_direito": "null",
}


def export_hidden_columns(
    full_access: bool,
    secretarias_acesso: list[str],
    include_coordinates: bool,
) -> set[str]:
    """Columns the CSV export must not emit for this user.

    Partial access hides every protocol-derived aggregate (global totals,
    `situacao`, other secretarias' counters/fractions) and the protocol
    columns of secretarias outside the user's reach. `latitude`/`longitude`
    are super-admin only. Base participant columns are always kept.
    """
    hidden: set[str] = set()
    if not full_access:
        hidden.update(EXPORT_GLOBAL_COLUMNS)
        allowed = set(secretarias_acesso)
        for secretaria, prefix in SECRETARIA_COLUMN_PREFIX.items():
            if secretaria in allowed:
                continue
            hidden.add(f"{prefix}_fracao")
            hidden.update(
                f"{prefix}_protocolos{'_total' if not suffix else suffix}"
                for suffix in ("", "_regular", "_irregular", "_atencao")
            )
        for protocolo_id, secretaria in PROTOCOLO_SECRETARIA.items():
            if secretaria not in allowed:
                hidden.add(protocolo_id)
    if not include_coordinates:
        hidden.update({"latitude", "longitude"})
    return hidden


def split_filters(
    filters: FilterCriteria,
) -> tuple[str | None, list[Any] | None, dict[str, list[str]], dict[str, list[Any]]]:
    """Split one `FilterCriteria` into (search, situacao, protocolo, column)
    filters with the exact v1 semantics used by the list pipeline."""
    filters_dict = filters.model_dump(exclude_none=True)
    search_term = filters_dict.pop("search", None)

    situacao_values: list[Any] | None = None
    if "situacao" in filters_dict:
        situacao_values = clean_values(split_values(filters_dict.pop("situacao")))
        if not situacao_values:
            situacao_values = None

    protocolo_filters: dict[str, list[str]] = {}
    for key, field in PROTOCOLO_FILTER_FIELDS.items():
        if key in filters_dict:
            values = clean_values([str(v) for v in split_values(filters_dict.pop(key))])
            if values:
                protocolo_filters[field] = values

    column_filters: dict[str, list[Any]] = {}
    for key, value in filters_dict.items():
        if key in FILTER_COLUMN_MAP:
            values = clean_values(split_values(value))
            if values:
                column_filters[FILTER_COLUMN_MAP[key]] = values

    if "cartao_pic_status" in filters_dict:
        cartao_values = clean_values(
            split_values(filters_dict.pop("cartao_pic_status"))
        )
        mapped: list[str] = []
        for value in cartao_values:
            key = str(value)
            if key not in CARTAO_PIC_STATUS_VALUES:
                raise ValidationError(
                    f"Valor inválido para cartao_pic_status: {value}"
                )
            mapped.append(CARTAO_PIC_STATUS_VALUES[key])
        if mapped:
            column_filters["has_cartao_pic"] = mapped

    return search_term, situacao_values, protocolo_filters, column_filters


def resolve_sort_column(
    sort_by: str | None,
    full_access: bool,
    allowed_secretarias: set[str] | None,
) -> str:
    """Request sort key -> wide column (same fallbacks as the list pipeline)."""
    sort_column = DEFAULT_SORT_COLUMN
    if sort_by and sort_by in SORTABLE_COLUMNS:
        if full_access:
            sort_column = SORTABLE_COLUMNS[sort_by]
        elif sort_by == "situacao":
            sort_column = DEFAULT_SORT_COLUMN
        elif sort_by in ("total_fracao", "total_irregular"):
            # "Total" sorts by irregularidade (fewer = better first).
            if allowed_secretarias and len(allowed_secretarias) == 1:
                prefix = SECRETARIA_COLUMN_PREFIX[next(iter(allowed_secretarias))]
                sort_column = f"{prefix}_protocolos_irregular"
            elif allowed_secretarias:
                sort_column = "total_protocolos_irregular"
            else:
                sort_column = DEFAULT_SORT_COLUMN
        else:
            sort_column = SORTABLE_COLUMNS[sort_by]
    return sort_column


def escape_ilike(value: str) -> str:
    """Escape ILIKE wildcards so the value matches literally."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def split_values(value: Any) -> list[Any]:
    """Split pipe-separated multi-select filter values (frontend convention)."""
    if isinstance(value, str) and "|" in value:
        return [v.strip() for v in value.split("|") if v.strip()]
    return [value]


def clean_values(values: list[Any]) -> list[Any]:
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


def apply_scalar_filter(
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

    if column == "has_cartao_pic":
        terms = [
            f"{column}.is.{v}" for v in values if v != "null"
        ] + [f"{column}.is.null" for v in values if v == "null"]
        if len(terms) > 1:
            return query.or_(",".join(terms))
        if terms[0] == f"{column}.is.null":
            return query.is_(column, "null")
        return query.filter(column, "is", terms[0].split(".")[-1])

    if column in EXACT_COLUMNS:
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
    return query.ilike(column, escape_ilike(str(values[0])))


def apply_wide_protocolo_filters(
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


def search_or_term(search_term: str) -> str:
    """PostgREST `or` filter for the free-text search (same 4 columns as before)."""
    pattern = f"%{escape_ilike(search_term)}%"
    return ",".join(f"{column}.ilike.{pattern}" for column in SEARCH_COLUMNS)


def validate_protocol_filter_access(
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
        if allowed_secretarias is not None and secretaria not in allowed_secretarias:
            raise ForbiddenError(f"Sem acesso a protocolos da secretaria {secretaria}")
    for secretaria in protocolo_filters.get("protocolo_secretaria") or []:
        if secretaria not in SECRETARIA_COLUMN_PREFIX:
            raise ValidationError(f"Secretaria desconhecida: {secretaria}")
        if allowed_secretarias is not None and secretaria not in allowed_secretarias:
            raise ForbiddenError(f"Sem acesso a protocolos da secretaria {secretaria}")


def list_select_columns(
    full_access: bool,
    secretarias_acesso: list[str],
    sort_by: str | None,
) -> list[str]:
    """Columns selected from `endpoint_participante_protocolos_wide`
    (participant columns plus the per-secretaria counters)."""
    columns = list(BASE_LIST_COLUMNS)
    if full_access:
        columns.extend(FULL_ACCESS_COLUMNS)
        sort_column = SORTABLE_COLUMNS.get(sort_by or "", DEFAULT_SORT_COLUMN)
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


def secretaria_access_terms(
    allowed_secretarias: set[str] | None,
    has_protocolo_filters: bool = False,
) -> tuple[str | None, bool]:
    """Secretaria restriction for partial access.

    The wide table has one row per participant, so partial access is
    restricted to the accessible secretarias via
    `or=(<prefix>_protocolos_total.gt.0,...)` (ANDed with any user-selected
    protocol filters). Returns `(or_terms, no_protocolo_match)`:

    - `or_terms`: the `or=` term list, or `None` when unrestricted;
    - `no_protocolo_match`: True when the user has no secretaria but protocol
      filters are active — such a user can never match them (v1 parity: empty
      result without querying).
    """
    if allowed_secretarias is None:
        return None, False
    if not allowed_secretarias:
        return None, has_protocolo_filters
    or_terms = ",".join(
        f"{SECRETARIA_COLUMN_PREFIX[secretaria]}_protocolos_total.gt.0"
        for secretaria in sorted(allowed_secretarias)
    )
    return or_terms, False
