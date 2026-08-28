"""Pure-Python port of the secretaria-based protocol governance.

Replaces the Polars implementation in `src/utils/secretaria_access.py` for
the PostgREST read-path (list/detail). The data-proxy RLS covers unit
filtering (cras/escola/cre/...), but the *secretaria* dimension still has to
be applied by the app: it filters each row's `protocolo_listagem` to the
user's allowed secretarias and recomputes counters, fractions and `situacao`.

Semantics are a faithful port of
`DataManager.apply_governance_filters` + `filter_and_recalculate_by_secretaria`:
- full access (all three secretarias): row returned unchanged;
- partial access: protocols filtered; rows with no remaining protocol are
  dropped (returned as `None`); counters/fractions/situacao recomputed;
  per-secretaria counters of disallowed secretarias become `None`;
- no access: row kept, but protocols emptied and every protocol-derived
  column (counters, fractions, situacao) set to `None`.
"""

from typing import Any

from src.utils.constants import SECRETARIA_COLUMN_PREFIX

ALL_SECRETARIAS = frozenset({"SME", "SMS", "SMAS"})

# total column has no suffix; the others carry "_irregular"/"_atencao"/"_regular".
_COUNTER_SUFFIXES = ("", "_irregular", "_atencao", "_regular")


def has_full_protocol_access(secretarias_acesso: list[str]) -> bool:
    """True when the user sees every protocol (no app-side filtering needed)."""
    return set(secretarias_acesso) >= ALL_SECRETARIAS


def _is_true(value: Any) -> bool:
    """Normalize `irregular_indicador` ("true"/"false" strings in BigQuery,
    booleans in Postgres JSON) to a Python bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "sim", "yes"}
    return False


def _counters(protocolos: list[dict[str, Any]]) -> dict[str, int]:
    """Compute total/irregular/atencao/regular counters from a protocol list."""
    return {
        "total": len(protocolos),
        "_irregular": sum(
            1 for p in protocolos if _is_true(p.get("irregular_indicador"))
        ),
        "_atencao": sum(
            1 for p in protocolos if p.get("protocolo_status_label") == "Atenção"
        ),
        "_regular": sum(
            1 for p in protocolos if p.get("protocolo_status_label") == "Regular"
        ),
    }


def _situacao(total: int, irregular: int, atencao: int) -> str:
    if total == 0:
        return "Sem protocolos"
    if irregular == 0:
        return "Regular"
    if atencao == 0:
        return "Irregular"
    return "Atenção"


def _fraction(regular: int | None, total: int | None) -> str | None:
    if regular is None or total is None:
        return None
    return f"{regular}/{total}"


def _counter_keys(prefix: str) -> list[str]:
    """Column names of the per-secretaria counters (total has a `_total` suffix)."""
    return [
        f"{prefix}_protocolos{'_total' if not suffix else suffix}"
        for suffix in _COUNTER_SUFFIXES
    ]


def _recalculate(
    row: dict[str, Any], protocolos: list[dict[str, Any]], allowed: set[str]
) -> None:
    """Recompute every protocol-derived column of `row` in place."""
    counts = _counters(protocolos)
    row["total_protocolos"] = counts["total"]
    row["total_protocolos_irregular"] = counts["_irregular"]
    row["total_protocolos_atencao"] = counts["_atencao"]
    row["total_protocolos_regular"] = counts["_regular"]
    row["situacao"] = _situacao(
        counts["total"], counts["_irregular"], counts["_atencao"]
    )
    row["total_fracao"] = _fraction(counts["_regular"], counts["total"])

    for secretaria, prefix in SECRETARIA_COLUMN_PREFIX.items():
        if secretaria in allowed:
            sec_protocolos = [
                p for p in protocolos if p.get("secretaria") == secretaria
            ]
            sec_counts = _counters(sec_protocolos)
            row[f"{prefix}_protocolos_total"] = sec_counts["total"]
            row[f"{prefix}_protocolos_irregular"] = sec_counts["_irregular"]
            row[f"{prefix}_protocolos_atencao"] = sec_counts["_atencao"]
            row[f"{prefix}_protocolos_regular"] = sec_counts["_regular"]
            row[f"{prefix}_fracao"] = _fraction(
                sec_counts["_regular"], sec_counts["total"]
            )
        else:
            for key in _counter_keys(prefix):
                row[key] = None
            row[f"{prefix}_fracao"] = None


def _null_protocol_columns(row: dict[str, Any]) -> None:
    """Zero out every protocol-derived column (no-access branch)."""
    row["protocolo_listagem"] = []
    for suffix in _COUNTER_SUFFIXES:
        row[f"total_protocolos{suffix}"] = None
    row["total_fracao"] = None
    for prefix in SECRETARIA_COLUMN_PREFIX.values():
        for key in _counter_keys(prefix):
            row[key] = None
        row[f"{prefix}_fracao"] = None
    row["situacao"] = None


def apply_secretaria_governance(
    row: dict[str, Any], secretarias_acesso: list[str]
) -> dict[str, Any] | None:
    """Apply secretaria governance to one participant row.

    Returns a new dict (never mutates the input), or `None` when the row must
    be dropped (partial access and no protocol left after filtering).
    """
    if has_full_protocol_access(secretarias_acesso):
        return row

    row = dict(row)
    protocolos = [
        p for p in (row.get("protocolo_listagem") or []) if isinstance(p, dict)
    ]

    if not secretarias_acesso:
        _null_protocol_columns(row)
        return row

    allowed = set(secretarias_acesso)
    filtered = [p for p in protocolos if p.get("secretaria") in allowed]
    if not filtered:
        return None

    row["protocolo_listagem"] = filtered
    _recalculate(row, filtered, allowed)
    return row


def apply_governance_to_rows(
    rows: list[dict[str, Any]], secretarias_acesso: list[str]
) -> list[dict[str, Any]]:
    """Govern every row, dropping the ones `apply_secretaria_governance` rejects."""
    if has_full_protocol_access(secretarias_acesso):
        return rows
    governed = [apply_secretaria_governance(row, secretarias_acesso) for row in rows]
    return [row for row in governed if row is not None]


def _normalized_values(values: list[str]) -> list[str]:
    return [str(v).lower().strip() for v in values if v and str(v).strip()]


def match_protocolo_filters(
    protocolos: list[dict[str, Any]], field_filters: dict[str, list[str]]
) -> bool:
    """Exact port of `_filter_array_column_combined_polars`.

    Case-insensitive; multiple filters must match the SAME array item; when a
    field has multiple values the row must match EVERY value (AND), each one
    together with the other fields.
    """
    normalized: dict[str, list[str]] = {}
    for field, values in field_filters.items():
        cleaned = _normalized_values(values)
        if cleaned:
            normalized[field] = cleaned
    if not normalized:
        return True

    multi_field: str | None = None
    multi_values: list[str] = []
    single_filters: dict[str, list[str]] = {}
    for field, values in normalized.items():
        if len(values) > 1 and multi_field is None:
            multi_field = field
            multi_values = values
        else:
            single_filters[field] = values

    def _field_value(protocolo: dict[str, Any], field: str) -> str:
        return str(protocolo.get(field, "")).lower().strip()

    def _matches_single(protocolo: dict[str, Any]) -> bool:
        return all(
            _field_value(protocolo, field) in values
            for field, values in single_filters.items()
        )

    if multi_field is None:
        return any(_matches_single(p) for p in protocolos)

    for value in multi_values:
        found = any(
            _field_value(p, multi_field) == value and _matches_single(p)
            for p in protocolos
        )
        if not found:
            return False
    return True


def match_situacao(row: dict[str, Any], values: list[str]) -> bool:
    """Case-insensitive `in` check against the row's (governed) `situacao`."""
    cleaned = _normalized_values(values)
    if not cleaned:
        return True
    return str(row.get("situacao") or "").lower().strip() in cleaned


def sort_rows(
    rows: list[dict[str, Any]], column: str, descending: bool
) -> list[dict[str, Any]]:
    """Sort dict rows by one column with `NULLS LAST`, like the Polars path."""

    def key(row: dict[str, Any]) -> Any:
        return row.get(column)

    non_null = [row for row in rows if row.get(column) is not None]
    null_rows = [row for row in rows if row.get(column) is None]
    non_null.sort(key=key, reverse=descending)
    return non_null + null_rows


# ---------------------------------------------------------------------------
# Resumo-based view (endpoint_participante_resumo)
# ---------------------------------------------------------------------------


def compute_resumo_view(
    row: dict[str, Any],
    full_access: bool,
    secretarias_acesso: list[str],
) -> dict[str, Any] | None:
    """Build the list view of one `endpoint_participante_resumo` row.

    - Full access: row returned as-is (fractions/counters are pre-aggregated).
    - No access: row kept, every protocol-derived field stays out (columns are
      not even selected by the repository), matching the v1 nulled view.
    - Partial access: `total_fracao` and `total_protocolos_irregular` are
      recomputed from the accessible secretarias' counters; `situacao` is
      hidden (`None`); rows with no accessible protocols are dropped (`None`).

    Returns a new dict (never mutates the input) or `None` to drop the row.
    """
    if full_access:
        return dict(row)

    row = dict(row)
    allowed = set(secretarias_acesso)
    if not allowed:
        for prefix in SECRETARIA_COLUMN_PREFIX.values():
            row[f"{prefix}_fracao"] = None
            for key in _counter_keys(prefix):
                row[key] = None
        row["total_fracao"] = None
        row["total_protocolos_irregular"] = None
        row["situacao"] = None
        return row

    regular_sum = 0
    total_sum = 0
    irregular_sum = 0
    for secretaria, prefix in SECRETARIA_COLUMN_PREFIX.items():
        if secretaria not in allowed:
            row[f"{prefix}_fracao"] = None
            for key in _counter_keys(prefix):
                row[key] = None
            continue
        regular_sum += row.get(f"{prefix}_protocolos_regular") or 0
        total_sum += row.get(f"{prefix}_protocolos_total") or 0
        irregular_sum += row.get(f"{prefix}_protocolos_irregular") or 0

    if total_sum == 0:
        return None

    row["total_protocolos_irregular"] = irregular_sum
    row["total_fracao"] = f"{regular_sum}/{total_sum}"
    row["situacao"] = None
    # Hidden key used only for in-app sorting by the combined fraction.
    row["_regular_sum"] = regular_sum
    return row
