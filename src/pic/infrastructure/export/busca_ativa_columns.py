"""CSV column map for the busca ativa event export (v2).

One CSV row per busca ativa event, combining the participant's identity/address
(from `endpoint_participante_protocolos_wide`, in the same shape as the
participant CSV) with the event's own fields (from `endpoint_busca_ativa`).
Identity/address columns are always visible; the SMS/SMAS event columns are
scoped to the intersection of the user's secretaria access and the selected
`busca_ativa` filter.

The merged row fed to `transform_busca_ativa_row` is a flat dict whose keys are
the participant wide-table origins (`endereco`, `complemento`, `bairro`,
`endereco_sms`, `nascimento_data`, `id_membro_familia`, `cpf`, `nome`) plus the
event fields (`fonte`, `data`, `sms_tipo_publico`, `smas_tipo`,
`smas_familia_localizada_indicador`, `smas_protocolo_violado`,
`smas_motivo_nao_localizada`, and the flattened `unidade_*` strings).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from src.pic.infrastructure.export.csv_columns import (
    _extract_endereco_sms,
    _format_date,
    _translate_busca_ativa,
)
from src.pic.infrastructure.repositories.helpers.participant_governance import (
    resolve_access,
)

BUSCA_ATIVA_CSV_COLUMNS: list[str] = [
    "id_membro_familia",
    "cpf",
    "nome",
    "nascimento_data",
    "endereco_smas",
    "complemento_endereco_smas",
    "bairro_endereco_smas",
    "endereco_sms",
    "complemento_endereco_sms",
    "bairro_endereco_sms",
    "fonte",
    "data_busca_ativa",
    "sms_tipo_publico",
    "smas_tipo",
    "smas_familia_localizada_indicador",
    "smas_protocolo_violado",
    "smas_motivo_nao_localizada",
    "unidade_sms_nome",
    "unidade_sms_equipe",
    "unidade_sms_regional",
    "unidade_smas_nome",
    "unidade_smas_regional",
]


def _join_array(value: Any) -> str | None:
    """Join a list of labels into a single `; `-separated cell (None if empty)."""
    if isinstance(value, list):
        joined = "; ".join(str(item) for item in value if item)
        return joined or None
    if value is None:
        return None
    return str(value)


# header -> (origin, transform). Columns absent from this map pass through
# (origin == header, no transform). `transform=None` means a pure rename.
BUSCA_ATIVA_TRANSFORMATIONS: dict[str, tuple[str, Callable[[Any], Any] | None]] = {
    "nascimento_data": ("nascimento_data", _format_date),
    "endereco_smas": ("endereco", None),
    "complemento_endereco_smas": ("complemento", None),
    "bairro_endereco_smas": ("bairro", None),
    "endereco_sms": ("endereco_sms", _extract_endereco_sms("endereco")),
    "complemento_endereco_sms": ("endereco_sms", _extract_endereco_sms("complemento")),
    "bairro_endereco_sms": ("endereco_sms", _extract_endereco_sms("bairro")),
    "data_busca_ativa": ("data", _format_date),
    "smas_tipo": ("smas_tipo", _join_array),
    "smas_familia_localizada_indicador": (
        "smas_familia_localizada_indicador",
        _translate_busca_ativa,
    ),
    "smas_protocolo_violado": ("smas_protocolo_violado", _join_array),
    "smas_motivo_nao_localizada": ("smas_motivo_nao_localizada", _join_array),
}


# Event columns owned by each secretaria (SME generates no events). Columns
# not listed here (identity/address + `fonte`/`data_busca_ativa`) are always
# present.
BUSCA_ATIVA_SECRETARIA_COLUMNS: dict[str, list[str]] = {
    "SMS": [
        "sms_tipo_publico",
        "unidade_sms_nome",
        "unidade_sms_equipe",
        "unidade_sms_regional",
    ],
    "SMAS": [
        "smas_tipo",
        "smas_familia_localizada_indicador",
        "smas_protocolo_violado",
        "smas_motivo_nao_localizada",
        "unidade_smas_nome",
        "unidade_smas_regional",
    ],
}

# Secretarias that originate busca ativa events (keys of the column map).
BUSCA_ATIVA_FONTES: frozenset[str] = frozenset(BUSCA_ATIVA_SECRETARIA_COLUMNS)


def selected_fontes_from_filter(raw: str | None) -> list[str] | None:
    """Parse the `busca_ativa` filter value into the selected event fontes.

    The frontend sends a pipe-separated list (`SMAS|SMS`); commas are accepted
    too for robustness. Returns `None` when the filter is absent (no recorte),
    and the subset of `{SMS, SMAS}` otherwise (possibly empty for an SME-only
    selection, which yields no events).
    """
    if not raw:
        return None
    tokens = re.split(r"[|,]", raw)
    return [
        token.strip().upper()
        for token in tokens
        if token.strip().upper() in BUSCA_ATIVA_FONTES
    ]


def _origin(header: str) -> str:
    if header in BUSCA_ATIVA_TRANSFORMATIONS:
        return BUSCA_ATIVA_TRANSFORMATIONS[header][0]
    return header


def _hidden_columns(
    secretarias_acesso: list[str],
    full_access: bool,
    fontes: list[str] | None = None,
) -> set[str]:
    """Event columns the user must not see.

    The visible secretarias are the intersection of the user's access (all of
    `{SMS, SMAS}` under full access) and, when present, the selected filter
    fontes. Columns of secretarias outside that intersection are hidden
    (mirrors the participant export's `export_hidden_columns`).
    """
    allowed = (
        set(BUSCA_ATIVA_FONTES)
        if full_access
        else set(secretarias_acesso) & BUSCA_ATIVA_FONTES
    )
    if fontes is not None:
        allowed &= set(fontes)
    hidden: set[str] = set()
    for secretaria, columns in BUSCA_ATIVA_SECRETARIA_COLUMNS.items():
        if secretaria not in allowed:
            hidden.update(columns)
    return hidden


def build_busca_ativa_header(
    permissions: Any = None, fontes: list[str] | None = None
) -> list[str]:
    """Deterministic CSV header for the busca ativa export.

    Scoped to the intersection of the user's secretaria access and the
    selected filter fontes (`fontes=None` means no filter recorte).
    `permissions=None` means full access.
    """
    secretarias_acesso, full_access = resolve_access(permissions)
    hidden = _hidden_columns(secretarias_acesso, full_access, fontes)
    return [h for h in BUSCA_ATIVA_CSV_COLUMNS if h not in hidden]


def transform_busca_ativa_row(row: dict[str, Any], headers: list[str]) -> list[Any]:
    """Transform one merged participant+event row into cells aligned with
    `headers` (same contract as `csv_columns.transform_row`).
    """
    values: list[Any] = []
    for header in headers:
        if header in BUSCA_ATIVA_TRANSFORMATIONS:
            origin, transform = BUSCA_ATIVA_TRANSFORMATIONS[header]
            raw = row.get(origin)
            values.append(transform(raw) if transform is not None else raw)
        else:
            values.append(row.get(_origin(header)))
    return values
