"""Sync of local `policy` rows into the data-proxy's `access_policy`.

Domain-specific on top of `postgrest_client` (which knows nothing about
`access_policy`'s columns). See plan.md sections 3.3, 5.

Write order: Postgres local is always the write of record (see
`HybridAdminRepository`); this module is only ever called *after* a local
commit succeeds, best-effort, and its failures are caught and logged by the
caller — never propagated to the admin request. A row that fails to sync
here is retried later by the login-time self-heal (`GET /admin/me`), driven
by `PolicyRow.synced_at`.

Two write shapes, mirroring the current `access_policy` schema (which no
longer has an `is_enabled` column — see plan.md section 3.3):

- Grant (`is_enabled=true`): idempotent upsert (`POST` with
  `Prefer: resolution=merge-duplicates` and
  `on_conflict=subject,unit_type,unit_id`). Batches are split only by
  serialized body size (`_UPSERT_CHUNK_BYTES`), so neither nginx's
  request-line limit (the historical 414) nor its default 1MB body limit is
  ever hit.
- Revoke (`is_enabled=false`): hard `DELETE` — a disabled row must
  disappear from the table, since the RLS check just sees what exists.
  Revokes are grouped by (subject, unit_type) and sent as
  `DELETE ...&unit_id=in.(...)`, chunked by URL-encoded byte budget
  (`_DELETE_URL_CHUNK_BYTES`): a grant set with thousands of unit ids
  (e.g. every school) stays well under nginx's request-line limit across a
  handful of requests. Deletes are idempotent — matching zero rows is a
  success (204), so a repeated revoke is harmless.
"""

import json
from datetime import UTC, datetime
from urllib.parse import quote_plus

from postgrest import AsyncPostgrestClient
from postgrest.types import ReturnMethod
from sqlalchemy import update

from src.pic.infrastructure.db.engine import get_session
from src.pic.infrastructure.db.models import PolicyRow
from src.pic.infrastructure.postgrest_client.client import (
    PostgrestClient,
    get_postgrest_client,
)
from src.utils.log import logger

# `access_policy` table in the data-proxy. The schema routing is determined
# by the Content-Profile header, which matches the configured data schema
# (config.PostgrestClientConfig.schema, e.g. `app_pequenos_cariocas`).
ACCESS_POLICY_TABLE = "access_policy"

# Unique constraint on `access_policy` (and on the local mirror `policy`)
# — see plan.md section 3.3.
ON_CONFLICT_COLUMNS = "subject,unit_type,unit_id"

# Max JSON body size per upsert `POST`. The nginx in front of the data-proxy
# applies its default `client_max_body_size` (1MB); this leaves headroom for
# any serialization larger than measured while keeping every request safely
# under that limit.
_UPSERT_CHUNK_BYTES = 500_000

# Max URL-encoded size of the `unit_id=in.(...)` filter value per revoke
# `DELETE`. Chunking by encoded bytes (not by id count) keeps the request
# line safely under nginx's default ~8KB limit regardless of how long the
# unit ids are (school codes can be large).
_DELETE_URL_CHUNK_BYTES = 4_000


def _upsert_chunks(
    rows: list[PolicyRow], payloads: list[dict]
) -> list[tuple[list[PolicyRow], list[dict]]]:
    """Split `rows`/`payloads` (same order) into batches whose payloads stay
    under `_UPSERT_CHUNK_BYTES` of serialized body. Preserves order; a single
    payload larger than the budget becomes a chunk of its own."""
    chunks: list[tuple[list[PolicyRow], list[dict]]] = []
    chunk_rows: list[PolicyRow] = []
    chunk_payloads: list[dict] = []
    chunk_bytes = 0
    for row, payload in zip(rows, payloads, strict=True):
        size = len(json.dumps(payload))
        if chunk_payloads and chunk_bytes + size > _UPSERT_CHUNK_BYTES:
            chunks.append((chunk_rows, chunk_payloads))
            chunk_rows, chunk_payloads, chunk_bytes = [], [], 0
        chunk_rows.append(row)
        chunk_payloads.append(payload)
        chunk_bytes += size
    if chunk_payloads:
        chunks.append((chunk_rows, chunk_payloads))
    return chunks


def _revoke_chunks(rows: list[PolicyRow]) -> list[list[PolicyRow]]:
    """Split revokes into `DELETE` batches: grouped by (subject, unit_type),
    then chunked so each request's `unit_id=in.(...)` filter value stays
    under `_DELETE_URL_CHUNK_BYTES` of URL-encoded bytes."""
    by_group: dict[tuple[str, str], list[PolicyRow]] = {}
    for row in rows:
        by_group.setdefault((row.subject, row.unit_type), []).append(row)

    chunks: list[list[PolicyRow]] = []
    for group_rows in by_group.values():
        chunk: list[PolicyRow] = []
        chunk_bytes = 0
        for row in group_rows:
            # `quote_plus` matches the query-string encoding httpx applies
            # to the `in.(...)` filter value; +1 for the separating comma.
            size = len(quote_plus(row.unit_id)) + 1
            if chunk and chunk_bytes + size > _DELETE_URL_CHUNK_BYTES:
                chunks.append(chunk)
                chunk, chunk_bytes = [], 0
            chunk.append(row)
            chunk_bytes += size
        if chunk:
            chunks.append(chunk)
    return chunks


class AccessPolicySync:
    """Best-effort push of local `policy` rows into `access_policy`."""

    def __init__(self, generic_client: PostgrestClient) -> None:
        self._client: AsyncPostgrestClient = generic_client.for_schema(
            generic_client._config.schema
        )

    async def push(self, rows: list[PolicyRow]) -> list[PolicyRow]:
        """Push every row's current state to the data-proxy, best-effort.

        Grants (`is_enabled=true`) are upserted (payload without any
        `is_enabled` field — the column no longer exists), in as few `POST`
        batches as `_UPSERT_CHUNK_BYTES` allows. Revokes (`is_enabled=false`)
        are hard-deleted, grouped by (subject, unit_type) and chunked by
        URL-encoded filter size — never one request per row and never a
        filter big enough to overflow nginx's request-line limit (the
        historical 414). Returns the subset of `rows` confirmed pushed;
        callers should leave `synced_at` unset on the rest so the next
        self-heal pass retries them.
        """
        if not rows:
            return []

        # Defensive dedup by primary key (keeps the last occurrence, i.e.
        # each row's current in-memory state): the very same `policy` row
        # can legitimately end up twice in `rows` if two local mutations
        # touched it in the same write (e.g. `HybridAdminRepository
        # .update_user`, which can both soft-disable and re-enable a row in
        # one call) — a single `upsert` batch with a repeated (schema,
        # subject, unit_type, unit_id) conflict key makes Postgres reject
        # the whole batch with "ON CONFLICT DO UPDATE command cannot affect
        # row a second time". Dedup by `row.id` rather than the natural key
        # so two genuinely distinct rows are never merged into one.
        rows = list({r.id: r for r in rows}.values())

        grants = [row for row in rows if row.is_enabled]
        # Confirmed revokes (`synced_at >= updated_at`) are already gone
        # from the data-proxy — skip them so a forced self-heal doesn't
        # re-DELETE on every fresh login. Pending ones (changed locally, or
        # a previous DELETE failed) must be retried.
        revokes = [
            row
            for row in rows
            if not row.is_enabled
            and (row.synced_at is None or row.synced_at < row.updated_at)
        ]

        pushed: list[PolicyRow] = []

        grant_payloads = [
            {
                "subject": row.subject,
                "is_admin": row.is_admin,
                "unit_type": row.unit_type,
                "unit_id": row.unit_id,
            }
            for row in grants
        ]
        for chunk_rows, chunk_payloads in _upsert_chunks(grants, grant_payloads):
            if await self._upsert(chunk_payloads):
                pushed.extend(chunk_rows)

        for chunk_rows in _revoke_chunks(revokes):
            if await self._delete(chunk_rows):
                pushed.extend(chunk_rows)

        return pushed

    async def _upsert(self, payload: list[dict]) -> bool:
        try:
            await (
                self._client.from_(ACCESS_POLICY_TABLE)
                .upsert(payload, on_conflict=ON_CONFLICT_COLUMNS)
                .execute()
            )
        except Exception:
            logger.exception(
                f"Falha ao sincronizar {len(payload)} grant(s) com access_policy"
            )
            return False
        return True

    async def _delete(self, rows: list[PolicyRow]) -> bool:
        subject = rows[0].subject
        unit_type = rows[0].unit_type
        unit_ids = [row.unit_id for row in rows]
        try:
            await (
                self._client.from_(ACCESS_POLICY_TABLE)
                .delete(returning=ReturnMethod.minimal)
                .eq("subject", subject)
                .eq("unit_type", unit_type)
                .in_("unit_id", unit_ids)
                .execute()
            )
        except Exception:
            logger.exception(
                f"Falha ao remover {len(rows)} revoke(s) de access_policy "
                f"(subject={subject}, unit_type={unit_type})"
            )
            return False
        return True


async def push_and_mark_synced(rows: list[PolicyRow]) -> None:
    """Push `rows` to the data-proxy best-effort, then stamp `synced_at` on
    whichever ones were confirmed pushed.

    Never raises — every failure is logged and simply left for the next
    self-heal pass (`synced_at` stays unset). `rows` must already be
    committed (have a primary key `id`); this is the shared entry point used
    both by `HybridAdminRepository`'s eager push after a local write and by
    the login-time self-heal in `GET /admin/me`. See plan.md section 5.
    """
    if not rows:
        return

    try:
        client = await get_postgrest_client()
        pushed = await AccessPolicySync(client).push(rows)
    except Exception:
        logger.exception("Falha ao inicializar sync com access_policy")
        return

    if not pushed:
        return

    now = datetime.now(UTC)
    ids = [row.id for row in pushed]
    async with get_session() as session:
        await session.execute(
            update(PolicyRow)
            .where(PolicyRow.id.in_(ids))
            # `updated_at` has `onupdate=func.now()`, which SQLAlchemy would
            # otherwise inject automatically into this UPDATE since it's not
            # in `.values()` — that server-side `now()` runs strictly after
            # the `synced_at` value above, so the row would immediately look
            # stale again (`synced_at < updated_at`) and be re-pushed on
            # every subsequent self-heal, forever. Pinning it to its current
            # value suppresses the auto-bump without touching the "real"
            # last-modified timestamp for a sync-only write.
            .values(synced_at=now, updated_at=PolicyRow.updated_at)
        )
        await session.commit()
