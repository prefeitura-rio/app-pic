"""Mappers from PostgREST JSON rows to participant domain entities.

Pure functions operating on plain dicts; no Polars involved anywhere.
"""

from typing import Any

from src.pic.domain.models.participante import Participante, ParticipanteListItem
from src.pic.infrastructure.repositories.helpers.participant_query_mapping import (
    LIST_ITEM_FIELDS,
)


def row_to_list_item(row: dict[str, Any]) -> ParticipanteListItem:
    """Map one `endpoint_participante_listagem` row to the lean list item.

    Only the fields of the v2 list envelope are kept; everything else is
    discarded so the response shape stays exactly the same as before.
    """
    return ParticipanteListItem(**{field: row.get(field) for field in LIST_ITEM_FIELDS})


def row_to_participante(row: dict[str, Any]) -> Participante:
    """Map one `endpoint_participante_listagem` row to the full entity.

    Pydantic validates/coerces types (dates, nested `endereco_sms` and
    `protocolo_listagem` JSON) and ignores columns the domain model doesn't
    declare (e.g. RLS unit columns such as `id_cras`).
    """
    return Participante(**row)
