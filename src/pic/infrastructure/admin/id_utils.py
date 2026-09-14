
import polars as pl

from src.core.security.permissions_models import IdWithName


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


def _convert_id_list_to_bq_struct(id_list: list[IdWithName] | None) -> str:
    if not id_list:
        return "NULL"

    structs = []
    for item in id_list:
        nome_escaped = item.nome.replace("'", "\\'")
        id_escaped = item.id.replace("'", "\\'")
        structs.append(f"STRUCT('{id_escaped}' AS id, '{nome_escaped}' AS nome)")

    return f"[{', '.join(structs)}]"
