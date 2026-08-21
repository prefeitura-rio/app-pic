
from typing import Any

import polars as pl

from src.core.security.permissions_models import IdWithName
from src.pic.domain.models.admin import UserAccessRecord

# unit_type -> (id_col, nome_col) on the participants dataframe.
# CRE has no dedicated name column: id doubles as its own display name.
UNIT_TYPE_COLUMNS: dict[str, tuple[str, str]] = {
    "id_cras": ("id_cras", "nome_cras"),
    "id_escola": ("id_escola", "nome_escola"),
    "id_cre": ("id_cre", "id_cre"),
    "id_ap": ("id_ap", "nome_ap"),
    "id_cas": ("id_cas", "nome_cas"),
    "id_clinica_familia": ("id_clinica_familia", "nome_clinica_familia"),
    "id_equipe_familia": ("id_equipe_familia", "nome_equipe_familia"),
}


def build_name_catalog(df: pl.DataFrame) -> dict[str, dict[str, str]]:
    """
    Build a {unit_type: {unit_id: nome}} catalog from the participants
    dataframe, used to resolve real display names for unit IDs stored
    (name-less) in Postgres policy rows.
    """
    catalog: dict[str, dict[str, str]] = {}

    for unit_type, (id_col, nome_col) in UNIT_TYPE_COLUMNS.items():
        if df.is_empty() or id_col not in df.columns:
            catalog[unit_type] = {}
            continue

        if nome_col not in df.columns or id_col == nome_col:
            unique_df = df.select(id_col).drop_nulls().unique()
            catalog[unit_type] = {
                str(row[id_col]): str(row[id_col]) for row in unique_df.to_dicts()
            }
            continue

        unique_df = df.select([id_col, nome_col]).drop_nulls().unique(subset=[id_col])
        catalog[unit_type] = {
            str(row[id_col]): str(row[nome_col]) for row in unique_df.to_dicts()
        }

    return catalog


def resolve_id_names(ids: list[str], catalog: dict[str, str]) -> list[IdWithName]:
    """Resolve a flat list of unit IDs into IdWithName using a name catalog.

    Falls back to id-as-name when an ID isn't found in the catalog (e.g.
    stale/removed unit), so nothing is silently dropped.
    """
    return [IdWithName(id=i, nome=catalog.get(i, i)) for i in ids]


_ID_LIST_KEYS = [
    "id_cras_list", "id_escola_list", "id_cre_list", "id_ap_list",
    "id_cas_list", "id_clinica_familia_list", "id_equipe_familia_list",
]


def build_user_access_record(row_dict: dict[str, Any]) -> UserAccessRecord:
    """Convert one `fetch_governance_df` row (already JSON-serializable, e.g.
    via `DataManager.df_to_json`) into a `UserAccessRecord`, turning each
    `id_*_list` cell (list of {"id", "nome"} dicts) into `IdWithName`."""
    row = dict(row_dict)
    for list_key in _ID_LIST_KEYS:
        if row.get(list_key):
            row[list_key] = [
                IdWithName(**item) if isinstance(item, dict) else item
                for item in row[list_key]
            ]
    return UserAccessRecord(**row)


def _extract_unique_ids(df: pl.DataFrame, id_col: str, nome_col: str) -> list[IdWithName]:
    if df.is_empty() or id_col not in df.columns:
        return []

    if nome_col not in df.columns or id_col == nome_col:
        unique_df = df.select(id_col).drop_nulls().unique().sort(id_col)
        return [
            IdWithName(id=str(row[id_col]), nome=str(row[id_col]))
            for row in unique_df.to_dicts()
        ]

    unique_df = (
        df.select([id_col, nome_col])
        .drop_nulls()
        .unique()
    )

    nome_to_ids = {}
    for row in unique_df.to_dicts():
        nome = str(row[nome_col])
        id_val = str(row[id_col])
        if nome not in nome_to_ids:
            nome_to_ids[nome] = []
        nome_to_ids[nome].append(id_val)

    result = []
    for nome in sorted(nome_to_ids.keys()):
        ids = nome_to_ids[nome]
        result.append(IdWithName(id=",".join(ids), nome=nome))

    return result
