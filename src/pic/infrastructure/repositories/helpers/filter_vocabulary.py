"""Pure-Python filter vocabulary computation for the PostgREST read path.

Replaces the Polars `DataManager.calculate_filter_options_fast` for
`GET /v2/filters`: every option list is derived from one PostgREST aggregate
query over `endpoint_participante_protocolos_wide` (one row per participant)
built by the repository. The aggregate rows are turned into `FilterOption`
items here, with no Polars involved.

Semantics are a faithful port of the old pipeline:

- scalar fields: one option per distinct value (id == label), natural sort;
- unit fields: id + nome pairs; ids sharing a label are joined with "|";
- protocol descriptions: the 14 per-protocol count columns of the wide
  table (one `col:col.count()` per protocol, aliased so the JSON keys carry
  the column name), labeled via the backend-owned
  `PROTOCOLO_DESCRICOES` map (columns with zero matches are dropped);
- protocol statuses: static, backend-owned list (no DB query);
- protocol secretarias: derived from the pre-aggregated counters
  (`<prefix>_protocolos_total:<prefix>_protocolos_total.max()`), intersected
  with user access;
- `situacoes` is only computed for full access (the filter is removed for
  partial/no access, v1 parity);
- protocol-derived fields are empty when the user has no secretaria access;
- `bolsa_familia` and `protocolo_secretarias` are now dynamic (previously
  hardcoded in the frontend).
"""

import re
from typing import Any

from src.pic.domain.models.filters import FilterOption
from src.pic.infrastructure.repositories.helpers.participant_query_mapping import (
    PROTOCOLO_SECRETARIA,
    PROTOCOLO_STATUS_COLUMNS,
)
from src.utils.constants import SECRETARIA_COLUMN_PREFIX

# ---------------------------------------------------------------------------
# Field configs: result key -> aggregate query shape + cascade exclusion.
# ---------------------------------------------------------------------------

# Kind: how the aggregate rows map to options.
# - "scalar": one column, id == label == value
# - "unit": id column + nome column, labels group ids with "|"
# - "bool": has_bolsa_familia column mapped to fixed labels
# - "wide_counts": single aggregate row with one `col:col.count()` per
#   protocol; columns with a count above zero become protocol options,
#   restricted to `allowed_secretarias` (access + selected secretaria)
# - "wide_secretarias": single aggregate row with the per-secretaria counter
#   maxima (`<prefix>_protocolos_total:<prefix>_protocolos_total.max()`);
#   maxima above zero mark the present secretarias, intersected with access
# - "static_status": fixed protocol status list (no DB query)
#
# `filter_key` is the `FilterCriteria` attribute excluded from the WHERE of
# this field's own query (cascade: all other active filters still apply).
# `full_access_only` skips the query unless the user has full access;
# `needs_access` skips the query when the user has no secretaria access.
# Every field reads `endpoint_participante_protocolos_wide` (one row per
# participant — protocol filters cascade as column/or filters).
FILTER_OPTION_CONFIGS: dict[str, dict[str, Any]] = {
    "bairros": {
        "kind": "scalar",
        "columns": ["bairro"],
        "filter_key": "bairro",
    },
    "subprefeituras": {
        "kind": "scalar",
        "columns": ["subprefeitura"],
        "filter_key": "subprefeitura",
    },
    "regioes_administrativas": {
        "kind": "scalar",
        "columns": ["regiao_administrativa"],
        "filter_key": "regiao_administrativa",
    },
    "grupos": {
        "kind": "scalar",
        "columns": ["grupo"],
        "filter_key": "grupo",
    },
    "cohorts": {
        "kind": "scalar",
        "columns": ["cohort"],
        "filter_key": "safra",
    },
    "status_list": {
        "kind": "scalar",
        "columns": ["status"],
        "filter_key": "status",
    },
    "situacoes": {
        "kind": "scalar",
        "columns": ["situacao"],
        "filter_key": "situacao",
        "full_access_only": True,
    },
    "racas": {
        "kind": "scalar",
        "columns": ["raca"],
        "filter_key": "raca",
    },
    "cres": {
        "kind": "unit",
        "columns": ["id_cre", "nome_cre"],
        "filter_key": "cre",
    },
    "aps": {
        "kind": "unit",
        "columns": ["id_ap", "nome_ap"],
        "filter_key": "ap",
    },
    "cas_list": {
        "kind": "unit",
        "columns": ["id_cas", "nome_cas"],
        "filter_key": "cas",
    },
    "cras": {
        "kind": "unit",
        "columns": ["id_cras", "nome_cras"],
        "filter_key": "cras",
    },
    "escolas": {
        "kind": "unit",
        "columns": ["id_escola", "nome_escola"],
        "filter_key": "escola",
    },
    "clinicas": {
        "kind": "unit",
        "columns": ["id_clinica_familia", "nome_clinica_familia"],
        "filter_key": "clinica",
    },
    "equipes_familia": {
        "kind": "unit",
        "columns": ["id_equipe_familia", "nome_equipe_familia"],
        "filter_key": "equipe_familia",
    },
    "protocolo_descricoes": {
        "kind": "wide_counts",
        "columns": PROTOCOLO_STATUS_COLUMNS,
        "filter_key": "protocolo_descricao",
        "needs_access": True,
    },
    "protocolo_status_list": {
        "kind": "static_status",
        "filter_key": "protocolo_status",
        "needs_access": True,
    },
    "bolsa_familia": {
        "kind": "bool",
        "columns": ["has_bolsa_familia"],
        "filter_key": "has_bolsa_familia",
    },
    "protocolo_secretarias": {
        "kind": "wide_secretarias",
        "filter_key": "protocolo_secretaria",
        "needs_access": True,
    },
}

BOLSA_FAMILIA_LABELS = {True: "Com Bolsa Família", False: "Sem Bolsa Família"}

SECRETARIA_LABELS = {
    "SME": "Educação (SME)",
    "SMAS": "Assistência (SMAS)",
    "SMS": "Saúde (SMS)",
}

SECRETARIA_ORDER = ["SME", "SMAS", "SMS"]

# Backend-owned protocol status list (fixed; v1 labels, natural sort at build).
PROTOCOLO_STATUS_VALUES = ["Regular", "Atenção", "Irregular"]

# Backend-owned source of truth for the protocol description labels
# (protocolo_id -> label). Kept in sync with
# `participant_query_mapping.PROTOCOLO_STATUS_COLUMNS`.
PROTOCOLO_DESCRICOES: dict[str, str] = {
    "smas_acesso_alimentacao": (
        "Criança com direito à alimentação adequada disponível"
    ),
    "smas_acesso_cpf_certidao_nascimento": (
        "Criança possui certidão de nascimento completa"
    ),
    "smas_cadunico_atualizado": (
        "Família da Criança e Gestante com o CadÚnico atualizado"
    ),
    "sme_frequencia_escolar": "Criança frequentando creche ou pré-escola",
    "sme_matriculado_creche": (
        "Criança de 6m a 3a11m inscrita para vaga de creche"
    ),
    "sme_matriculado_pre_escola": (
        "Criança de 4 a 5a11m matriculada na pré-escola"
    ),
    "sms_consulta_puerperal": (
        "Gestante com consulta puerperal até 7 dias após o parto"
    ),
    "sms_consultas_minimas_infantil": (
        "Criança com no mínimo 7 consultas no primeiro ano de vida, "
        "2 consultas no segundo ano de vida e 1 consulta anual até os "
        "5 anos, 11 meses e 29 dias de idade"
    ),
    "sms_consultas_pre_natal": (
        "Gestante com número mínimo de consultas de pré-natal conforme "
        "a idade gestacional"
    ),
    "sms_gestantes_testes_rapidos": (
        "Gestante com testes rápidos realizados até a 20ª semana"
    ),
    "sms_possui_equipe_familia": (
        "Gestante e/ou criança vinculada à uma Equipe de Saúde da Família "
        "ou Unidade de Atenção Primária"
    ),
    "sms_vacinacao_pentavalente": (
        "Criança com 3ª dose da vacina pentavalente no 1 ano"
    ),
    "sms_visitas_domiciliares_infantil": (
        "Criança com 2 visitas domiciliares anuais do ACS "
        "(0–5 anos, 11 meses e 29 dias de idade)"
    ),
    "sms_visitas_domiciliares_puerperio": (
        "Gestante com 4 visitas domiciliares do ACS, sendo 1 no puerpério"
    ),
}


def _natural_sort_key(text: str) -> tuple:
    """Natural sort: numbers at the start of the string sort numerically."""
    match = re.match(r"^(\d+)", text)
    if match:
        return (int(match.group(1)), text)
    return (float("inf"), text)


def _non_empty(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def _scalar_options(column: str, rows: list[dict[str, Any]]) -> list[FilterOption]:
    values = sorted(
        {str(row[column]) for row in rows if _non_empty(row.get(column))},
        key=_natural_sort_key,
    )
    return [FilterOption(id=value, label=value) for value in values]


def _unit_options(
    id_column: str, label_column: str, rows: list[dict[str, Any]]
) -> list[FilterOption]:
    """id + nome pairs; ids sharing a label are joined with "|" (v1 parity)."""
    label_to_ids: dict[str, list[str]] = {}
    seen_pairs: set[tuple[str, str]] = set()
    for row in rows:
        id_value = row.get(id_column)
        if not _non_empty(id_value):
            continue
        id_str = str(id_value)
        label = (
            str(row[label_column])
            if _non_empty(row.get(label_column))
            else id_str
        )
        pair = (id_str, label)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        label_to_ids.setdefault(label, []).append(id_str)

    options = [
        FilterOption(id="|".join(ids), label=label)
        for label, ids in label_to_ids.items()
    ]
    options.sort(key=lambda opt: _natural_sort_key(opt.label))
    return options


def _bool_options(column: str, rows: list[dict[str, Any]]) -> list[FilterOption]:
    present = {row[column] for row in rows if row.get(column) is not None}
    return [
        FilterOption(id=str(value).lower(), label=BOLSA_FAMILIA_LABELS[value])
        for value in (True, False)
        if value in present
    ]


def _secretaria_options(
    rows: list[dict[str, Any]],
    allowed_secretarias: set[str] | None,
) -> list[FilterOption]:
    """Secretarias present in the filtered view, intersected with user access.

    Reads the single-row aggregate of the per-secretaria counter maxima
    (`<prefix>_protocolos_total.max()`); a secretaria is present when its
    maximum is above zero (NULL counts as absent).
    """
    row = rows[0] if rows else {}
    present = {
        secretaria
        for secretaria, prefix in SECRETARIA_COLUMN_PREFIX.items()
        if (row.get(f"{prefix}_protocolos_total") or 0) > 0
    }
    if allowed_secretarias is not None:
        present &= allowed_secretarias
    return [
        FilterOption(id=secretaria, label=SECRETARIA_LABELS[secretaria])
        for secretaria in SECRETARIA_ORDER
        if secretaria in present
    ]


def _wide_counts_options(
    rows: list[dict[str, Any]],
    allowed_secretarias: set[str] | None = None,
) -> list[FilterOption]:
    """Protocol options from the single-row `<col>.count()` aggregate.

    Columns with a count above zero are the protocols present among the
    remaining participants; labels come from the backend-owned map. Protocols
    of secretarias outside `allowed_secretarias` (partial access and/or the
    selected secretaria filter) are dropped even when present in the rows.
    """
    row = rows[0] if rows else {}
    options = [
        FilterOption(id=protocolo_id, label=label)
        for protocolo_id, label in PROTOCOLO_DESCRICOES.items()
        if (row.get(protocolo_id) or 0) > 0
        and (
            allowed_secretarias is None
            or PROTOCOLO_SECRETARIA.get(protocolo_id) in allowed_secretarias
        )
    ]
    options.sort(key=lambda opt: _natural_sort_key(opt.label))
    return options


def _static_status_options() -> list[FilterOption]:
    """Fixed protocol status list (backend-owned, natural sort)."""
    values = sorted(PROTOCOLO_STATUS_VALUES, key=_natural_sort_key)
    return [FilterOption(id=value, label=value) for value in values]


def build_options(
    config: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    allowed_secretarias: set[str] | None = None,
) -> list[FilterOption]:
    """Turn one field's aggregate rows into its option list."""
    kind = config["kind"]
    if kind == "scalar":
        return _scalar_options(config["columns"][0], rows)
    if kind == "unit":
        return _unit_options(config["columns"][0], config["columns"][1], rows)
    if kind == "bool":
        return _bool_options(config["columns"][0], rows)
    if kind == "wide_counts":
        return _wide_counts_options(rows, allowed_secretarias)
    if kind == "wide_secretarias":
        return _secretaria_options(rows, allowed_secretarias)
    if kind == "static_status":
        return _static_status_options()
    raise ValueError(f"Unknown filter option kind: {kind}")
