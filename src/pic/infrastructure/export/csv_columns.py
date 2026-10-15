"""Fixed CSV column map for the participant export (v2).

The export pages arrive as raw wide-table rows (`select("*")`, already stripped
of columns outside the user's reach). This module is the single source of truth
that turns those rows into a deterministic CSV:

- `EXPORT_CSV_COLUMNS` — ordered list of participant headers (post-rename, with
  the `endereco_sms` JSON split into three columns). No protocol columns here.
- `CSV_TRANSFORMATIONS` — header -> (origin, transform): renames, the
  `endereco_sms` split, business labels for the boolean flags, and date
  formatting. Columns not listed here pass through unchanged (origin == header).
- `build_export_header(hidden)` / `transform_row(row, headers)` — apply the map
  to produce the deterministic, visibility-filtered header and the transformed
  cell values for a row.

The header is never derived from the row keys; any column of the wide table not
present in the map (e.g. `cpf_particao`) is silently dropped.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from typing import Any

from src.pic.infrastructure.repositories.helpers.participant_query_mapping import (
    PROTOCOLO_STATUS_COLUMNS,
)

# ---------------------------------------------------------------------------
# Value transformers
# ---------------------------------------------------------------------------


def _format_date(value: Any) -> str | None:
    """ISO date/datetime -> ``DD/MM/AAAA``; unparseable -> ``None`` (``""``)."""
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    try:
        return date.fromisoformat(str(value).strip()).strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return None


def _translate_bool(
    value: Any, true_label: str, false_label: str, null_label: str
) -> str | None:
    """Translate a boolean flag to a business label.

    Only ``True``/``False``/``None`` are recognised; any other value (unexpected
    string, etc.) yields an empty cell.
    """
    if value is True:
        return true_label
    if value is False:
        return false_label
    if value is None:
        return null_label
    return None


def _translate_cartao_pic(value: Any) -> str | None:
    return _translate_bool(value, "retirado", "não retirado", "sem direito")


def _translate_bolsa_familia(value: Any) -> str | None:
    return _translate_bool(value, "beneficiário", "não beneficiário", "-")


def _translate_cobertura(value: Any) -> str | None:
    return _translate_bool(value, "SIM", "NÃO", "-")


def _parse_endereco_sms(value: Any) -> dict | None:
    """Normalise ``endereco_sms`` (Postgres JSON dict or BigQuery JSON string)."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return None
    return value if isinstance(value, dict) else None


def _extract_endereco_sms(key: str) -> Callable[[Any], Any]:
    def _extract(value: Any) -> Any:
        parsed = _parse_endereco_sms(value)
        return parsed.get(key) if parsed else None

    return _extract


# ---------------------------------------------------------------------------
# Column map
# ---------------------------------------------------------------------------

# Ordered participant headers (post-rename/split). Mirrors the wide-table column
# order previously captured by `EXPORT_FALLBACK_COLUMNS`, minus `cpf_particao`.
EXPORT_CSV_COLUMNS: list[str] = [
    "id_familia",
    "id_membro_familia",
    "nome",
    "cpf",
    "grupo",
    "bairro_endereco_smas",
    "idade",
    "status",
    "situacao",
    "raca",
    "nascimento_data",
    "endereco_smas",
    "complemento_endereco_smas",
    "endereco_sms",
    "complemento_endereco_sms",
    "bairro_endereco_sms",
    "telefone_1_ddd",
    "telefone_1_numero",
    "telefone_2_ddd",
    "telefone_2_numero",
    "subprefeitura",
    "regiao_administrativa",
    "cohort",
    "status_bolsa_familia",
    "status_cartao_pic",
    "latitude",
    "longitude",
    "total_fracao",
    "total_protocolos",
    "total_protocolos_regular",
    "total_protocolos_irregular",
    "total_protocolos_atencao",
    "assistencia_fracao",
    "assistencia_protocolos_total",
    "assistencia_protocolos_regular",
    "assistencia_protocolos_irregular",
    "assistencia_protocolos_atencao",
    "educacao_fracao",
    "educacao_protocolos_total",
    "educacao_protocolos_regular",
    "educacao_protocolos_irregular",
    "educacao_protocolos_atencao",
    "saude_fracao",
    "saude_protocolos_total",
    "saude_protocolos_regular",
    "saude_protocolos_irregular",
    "saude_protocolos_atencao",
    "id_cre",
    "nome_cre",
    "id_escola",
    "nome_escola",
    "source_escola",
    "id_cas",
    "nome_cas",
    "id_cras",
    "nome_cras",
    "source_cras",
    "id_ap",
    "nome_ap",
    "id_clinica_familia",
    "nome_clinica_familia",
    "source_clinica_familia",
    "possui_cobertura_clinica_da_familia",
    "id_equipe_familia",
    "nome_equipe_familia",
    "source_equipe_familia",
    "possui_cobertura_equipe_de_familia",
    "equipe_familia",
]

# header -> (origin, transform). Columns absent from this map are passthrough
# (origin == header, no transform). `transform=None` means a pure rename.
CSV_TRANSFORMATIONS: dict[str, tuple[str, Callable[[Any], Any] | None]] = {
    "bairro_endereco_smas": ("bairro", None),
    "endereco_smas": ("endereco", None),
    "complemento_endereco_smas": ("complemento", None),
    "endereco_sms": ("endereco_sms", _extract_endereco_sms("endereco")),
    "complemento_endereco_sms": ("endereco_sms", _extract_endereco_sms("complemento")),
    "bairro_endereco_sms": ("endereco_sms", _extract_endereco_sms("bairro")),
    "status_bolsa_familia": ("has_bolsa_familia", _translate_bolsa_familia),
    "status_cartao_pic": ("has_cartao_pic", _translate_cartao_pic),
    "possui_cobertura_clinica_da_familia": (
        "has_cobertura_clinica_familia",
        _translate_cobertura,
    ),
    "possui_cobertura_equipe_de_familia": (
        "has_cobertura_equipe_familia",
        _translate_cobertura,
    ),
    "nascimento_data": ("nascimento_data", _format_date),
    "cohort": ("cohort", _format_date),
}

# Protocol column renames (wide-table column name -> CSV header). The data-proxy
# column names stay untouched; only the emitted CSV header changes. Protocols
# absent from this map pass through (header == origin).
PROTOCOL_CSV_RENAMES: dict[str, str] = {
    "sme_frequencia_escolar": "sme_frequencia_creche_escola",
}

_PROTOCOL_HEADER_TO_ORIGIN = {
    header: origin for origin, header in PROTOCOL_CSV_RENAMES.items()
}


def _origin(header: str) -> str:
    if header in CSV_TRANSFORMATIONS:
        return CSV_TRANSFORMATIONS[header][0]
    return _PROTOCOL_HEADER_TO_ORIGIN.get(header, header)


def build_export_header(hidden: set[str]) -> list[str]:
    """Deterministic, visibility-filtered CSV header.

    Participant columns in `EXPORT_CSV_COLUMNS` order followed by the protocol
    columns in `PROTOCOLO_STATUS_COLUMNS` order (renamed via
    `PROTOCOL_CSV_RENAMES`); columns whose origin is in `hidden` (see
    `export_hidden_columns`) are omitted.
    """
    header = [h for h in EXPORT_CSV_COLUMNS if _origin(h) not in hidden]
    header.extend(
        PROTOCOL_CSV_RENAMES.get(p, p)
        for p in PROTOCOLO_STATUS_COLUMNS
        if p not in hidden
    )
    return header


def transform_row(row: dict[str, Any], headers: list[str]) -> list[Any]:
    """Transform one wide-table row into cells aligned with `headers`.

    Transformed columns use their origin + transform; every other header (both
    passthrough participant columns and protocol columns, including renamed
    protocols) reads the row value from its origin (the CSV escaper handles
    quoting/None).
    """
    values: list[Any] = []
    for header in headers:
        if header in CSV_TRANSFORMATIONS:
            origin, transform = CSV_TRANSFORMATIONS[header]
            raw = row.get(origin)
            values.append(transform(raw) if transform is not None else raw)
        else:
            values.append(row.get(_origin(header)))
    return values
