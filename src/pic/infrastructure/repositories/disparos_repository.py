"""PostgREST implementation of the disparos read repository.

Reads `endpoint_whatsapp_disparo` (BigQuery table exposed by the data-proxy,
one row per participant x campaign) filtered by `id_membro_familia`. The
request carries the end user's JWT (`with_user_token`) so the data-proxy
applies RLS; the read is best-effort — a PostgREST/transport failure is
logged and degrades to `None` so the participant detail stays up.
"""

from datetime import datetime
from typing import Any

from src.pic.application.ports.disparos_repository import DisparosRepository
from src.pic.domain.models.disparo import Disparo, DisparoMetadados
from src.pic.infrastructure.postgrest_client.client import PostgrestClient
from src.pic.infrastructure.postgrest_client.errors import PostgrestError
from src.pic.infrastructure.postgrest_client.pagination import fetch_pages
from src.utils.log import logger

TABLE_DISPAROS = "endpoint_whatsapp_disparo"

# Columns of the disparo entry (dictionary of REFINAMENTO.md). The RLS/unit
# columns and participant identifiers are not selected — only what the DTO
# exposes.
_DISPARO_COLUMNS = [
    "disparo_data",
    "disparo_datahora",
    "disparo_jornada",
    "disparo_secretaria_sigla",
    "disparo_status",
    "disparo_falha_indicador",
    "disparo_total_quantidade",
    "disparo_entregues_quantidade",
    "disparo_falhas_quantidade",
]

_DISPARO_SELECT = ",".join(_DISPARO_COLUMNS)


def _row_to_disparo(row: dict[str, Any]) -> Disparo:
    """Map one `endpoint_whatsapp_disparo` row to the domain model."""

    def _get(column: str) -> Any:
        return row.get(column)

    metadados_values = {
        "total_ultimos_30d": _get("disparo_total_quantidade"),
        "entregues_30d": _get("disparo_entregues_quantidade"),
        "falhas_30d": _get("disparo_falhas_quantidade"),
    }
    has_metadados = any(value is not None for value in metadados_values.values())

    return Disparo(
        campanha=_get("disparo_jornada"),
        data=_get("disparo_data"),
        datahora=_get("disparo_datahora"),
        secretaria=_get("disparo_secretaria_sigla"),
        status=_get("disparo_status"),
        indicador_falha=_get("disparo_falha_indicador"),
        metadados=DisparoMetadados(**metadados_values) if has_metadados else None,
    )


def _sort_newest_first(disparos: list[Disparo]) -> list[Disparo]:
    """Most recent campaign first; entries without `datahora` go last."""
    return sorted(
        disparos,
        key=lambda d: d.datahora or datetime.min,
        reverse=True,
    )


class PostgrestDisparosRepository(DisparosRepository):
    """Disparos reads straight from the data-proxy PostgREST."""

    def __init__(self, client: PostgrestClient) -> None:
        self._client = client

    async def get_disparos(
        self,
        id_membro_familia: str,
        user_token: str | None = None,
    ) -> list[Disparo] | None:
        try:
            async with self._client.with_user_token(user_token):
                rows, _ = await fetch_pages(
                    self._client,
                    lambda count=None: (
                        self._client.table(TABLE_DISPAROS)
                        .select(_DISPARO_SELECT)
                        .filter(
                            "id_membro_familia", "eq", str(id_membro_familia)
                        )
                    ),
                    limit=None,
                    with_count=False,
                )
        except PostgrestError as error:
            logger.warning(
                f"[disparos] fetch failed for "
                f"id_membro_familia={id_membro_familia}: {error}"
            )
            return None

        disparos = [_row_to_disparo(dict(row)) for row in rows]
        logger.info(
            f"[disparos] fetched {len(disparos)} campaign(s) for "
            f"id_membro_familia={id_membro_familia}"
        )
        return _sort_newest_first(disparos)
