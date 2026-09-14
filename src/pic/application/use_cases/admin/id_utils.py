from typing import Any

import polars as pl

from src.pic.domain.models.admin import IdWithName, UserAccessRecord

_ID_LIST_KEYS = [
    "id_cras_list", "id_escola_list", "id_cre_list", "id_ap_list",
    "id_cas_list", "id_clinica_familia_list", "id_equipe_familia_list",
]


def df_to_json(df: pl.DataFrame) -> list[dict[str, Any]]:
    """Polars DataFrame -> list of dicts (JSON-safe; empty df -> [])."""
    if df.is_empty():
        return []
    return df.to_dicts()


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
