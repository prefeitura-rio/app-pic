"""PostgREST implementation of the busca ativa read repository.

Reads `endpoint_busca_ativa` (BigQuery table exposed by the data-proxy, one
row per busca ativa event) filtered by `id_membro_familia`. The request
carries the end user's JWT (`with_user_token`) so the data-proxy applies
RLS; the read is best-effort — a PostgREST/transport failure is logged and
degrades to `None` so the participant detail stays up.

Ordering is `data desc, id_busca_ativa asc` (stable across offset pages) and
pagination uses the shared `fetch_pages` helper (PGRST cap of 1000 rows per
page).

Secretaria governance is applied app-side: `resolve_access` maps the caller's
permissions to `(secretarias_acesso, full_access)`. Full access reads all
events; partial access filters `fonte` to the intersection of the user's
secretarias with `{SMS, SMAS}`; no SMS/SMAS access short-circuits without
touching the data-proxy.

The per-participant read (`get_busca_ativa`) degrades to `None` on a
data-proxy failure; the bulk export read (`get_busca_ativa_for_members`)
raises instead, so a CSV export never silently drops events.
"""

import asyncio
from typing import Any

from src.pic.application.ports.busca_ativa_repository import (
    BuscaAtivaRepository,
)
from src.pic.domain.models.busca_ativa import (
    BuscaAtivaEvento,
    BuscaAtivaUnidadeReferenciada,
    BuscaAtivaUnidadeSMAS,
    BuscaAtivaUnidadeSMS,
)
from src.pic.infrastructure.postgrest_client.client import PostgrestClient
from src.pic.infrastructure.postgrest_client.errors import PostgrestError
from src.pic.infrastructure.postgrest_client.pagination import fetch_pages
from src.pic.infrastructure.repositories.helpers.participant_governance import (
    resolve_access,
)
from src.utils.log import logger

TABLE_BUSCA_ATIVA = "endpoint_busca_ativa"

# Secretarias que originam eventos de busca ativa (SME não gera eventos).
BUSCA_ATIVA_SECRETARIAS = frozenset({"SMS", "SMAS"})

# Columns of the busca ativa event (dicionário de dados: schema.json). The
# participant identifiers are not selected. `unidade_referenciada` is a STRUCT
# returned as JSON by PostgREST and mapped to submodels (sme is discarded).
_BUSCA_ATIVA_COLUMNS = [
    "id_busca_ativa",
    "fonte",
    "data",
    "sms_tipo_publico",
    "smas_tipo",
    "smas_familia_localizada_indicador",
    "smas_protocolo_violado",
    "smas_motivo_nao_localizada",
    "processed_at",
    "unidade_referenciada",
]

_BUSCA_ATIVA_SELECT = ",".join(_BUSCA_ATIVA_COLUMNS)

# Bulk select includes the participant identifier so the caller can group
# events back to their participant. (The per-participant read omits it.)
_BUSCA_ATIVA_MEMBERS_SELECT = "id_membro_familia," + _BUSCA_ATIVA_SELECT

# Max ids per `id_membro_familia=in.(...)` request: keeps the query URL well
# within proxy/PostgREST limits (ids are ~11 chars each).
_BUSCA_ATIVA_IN_CHUNK = 250


def _fontes_autorizadas(secretarias_acesso: list[str], full_access: bool) -> list[str] | None:
    """Fonte filter for the secretaria recorte.

    Returns `None` when the user should see every fonte (full access), `[]`
    when the user has no SMS/SMAS access at all, and the ordered list of
    allowed fontes otherwise.
    """
    if full_access:
        return None
    return sorted(set(secretarias_acesso) & BUSCA_ATIVA_SECRETARIAS)


def _as_list(value: Any) -> list[str]:
    return list(value) if isinstance(value, list) else []


def _map_unidade(raw: Any) -> BuscaAtivaUnidadeReferenciada | None:
    """Map the `unidade_referenciada` STRUCT (JSON dict) to submodels."""
    if not isinstance(raw, dict):
        return None

    sms_raw = raw.get("sms")
    smas_raw = raw.get("smas")

    sms = None
    if isinstance(sms_raw, dict):
        sms = BuscaAtivaUnidadeSMS(
            nome=sms_raw.get("nome"),
            regional=sms_raw.get("regional"),
            equipe_nome=sms_raw.get("equipe_nome"),
        )

    smas = None
    if isinstance(smas_raw, dict):
        smas = BuscaAtivaUnidadeSMAS(
            nome=smas_raw.get("nome"),
            regional=smas_raw.get("regional"),
        )

    if sms is None and smas is None:
        return None

    return BuscaAtivaUnidadeReferenciada(sms=sms, smas=smas)


def _row_to_busca_ativa(row: dict[str, Any]) -> BuscaAtivaEvento:
    """Map one `endpoint_busca_ativa` row to the domain model."""
    return BuscaAtivaEvento(
        id_busca_ativa=row.get("id_busca_ativa"),
        fonte=row.get("fonte"),
        data=row.get("data"),
        sms_tipo_publico=row.get("sms_tipo_publico"),
        smas_tipo=_as_list(row.get("smas_tipo")),
        smas_familia_localizada_indicador=row.get("smas_familia_localizada_indicador"),
        smas_protocolo_violado=_as_list(row.get("smas_protocolo_violado")),
        smas_motivo_nao_localizada=_as_list(row.get("smas_motivo_nao_localizada")),
        processed_at=row.get("processed_at"),
        unidade_referenciada=_map_unidade(row.get("unidade_referenciada")),
    )


class PostgrestBuscaAtivaRepository(BuscaAtivaRepository):
    """Busca ativa reads straight from the data-proxy PostgREST."""

    def __init__(self, client: PostgrestClient) -> None:
        self._client = client

    def _build_query(self, id_membro_familia: str, fontes: list[str] | None):
        query = (
            self._client.table(TABLE_BUSCA_ATIVA)
            .select(_BUSCA_ATIVA_SELECT)
            .filter("id_membro_familia", "eq", str(id_membro_familia))
            .order("data", desc=True, nullsfirst=False)
            .order("id_busca_ativa", desc=False, nullsfirst=False)
        )
        if fontes:
            query = query.filter("fonte", "in", f"({','.join(fontes)})")
        return query

    def _build_members_query(self, ids: list[str], fontes: list[str] | None):
        query = (
            self._client.table(TABLE_BUSCA_ATIVA)
            .select(_BUSCA_ATIVA_MEMBERS_SELECT)
            .filter("id_membro_familia", "in", f"({','.join(ids)})")
            .order("data", desc=True, nullsfirst=False)
            .order("id_busca_ativa", desc=False, nullsfirst=False)
        )
        if fontes:
            query = query.filter("fonte", "in", f"({','.join(fontes)})")
        return query

    async def get_busca_ativa(
        self,
        id_membro_familia: str,
        *,
        user_token: str | None = None,
        offset: int = 0,
        limit: int = 20,
        permissions: Any = None,
    ) -> list[BuscaAtivaEvento] | None:
        secretarias_acesso, full_access = resolve_access(permissions)
        fontes = _fontes_autorizadas(secretarias_acesso, full_access)
        if fontes is not None and not fontes:
            return []

        try:
            async with self._client.with_user_token(user_token):
                rows, _ = await fetch_pages(
                    self._client,
                    lambda count=None: self._build_query(
                        id_membro_familia, fontes
                    ),
                    limit=limit,
                    with_count=False,
                    start_offset=offset,
                )
        except PostgrestError as error:
            logger.warning(
                f"[busca_ativa] fetch failed for "
                f"id_membro_familia={id_membro_familia}: {error}"
            )
            return None

        eventos = [_row_to_busca_ativa(dict(row)) for row in rows]
        logger.info(
            f"[busca_ativa] fetched {len(eventos)} event(s) for "
            f"id_membro_familia={id_membro_familia}"
        )
        return eventos

    async def get_busca_ativa_for_members(
        self,
        ids: list[str],
        *,
        user_token: str | None = None,
        permissions: Any = None,
        fontes: list[str] | None = None,
    ) -> list[tuple[str, BuscaAtivaEvento]]:
        secretarias_acesso, full_access = resolve_access(permissions)
        autorizadas = _fontes_autorizadas(secretarias_acesso, full_access)
        if fontes is None:
            efetivas = autorizadas
        elif autorizadas is None:
            efetivas = sorted(set(fontes) & BUSCA_ATIVA_SECRETARIAS)
        else:
            efetivas = sorted(set(autorizadas) & set(fontes))
        if efetivas is not None and not efetivas:
            return []
        if not ids:
            return []

        async with self._client.with_user_token(user_token):
            chunks = [
                ids[index : index + _BUSCA_ATIVA_IN_CHUNK]
                for index in range(0, len(ids), _BUSCA_ATIVA_IN_CHUNK)
            ]
            try:
                rows_per_chunk = await asyncio.gather(
                    *(
                        fetch_pages(
                            self._client,
                            lambda count=None, chunk=chunk: self._build_members_query(
                                chunk, efetivas
                            ),
                            limit=None,
                            with_count=False,
                        )
                        for chunk in chunks
                    )
                )
            except PostgrestError as error:
                logger.warning(
                    f"[busca_ativa] bulk fetch failed for {len(ids)} member(s): "
                    f"{error}"
                )
                raise

        resultado: list[tuple[str, BuscaAtivaEvento]] = []
        for rows, _ in rows_per_chunk:
            for row in rows:
                id_membro_familia = row.get("id_membro_familia")
                if id_membro_familia is None:
                    continue
                resultado.append(
                    (str(id_membro_familia), _row_to_busca_ativa(dict(row)))
                )
        logger.info(
            f"[busca_ativa] bulk fetched {len(resultado)} event(s) for "
            f"{len(ids)} member(s)"
        )
        return resultado
