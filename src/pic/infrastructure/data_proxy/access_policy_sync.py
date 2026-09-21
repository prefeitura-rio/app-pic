"""Sync of local `policy` rows into the data-proxy's `access_policy`.

Domain-specific on top of `postgrest_client` (which knows nothing about
`access_policy`'s columns). See plan.md sections 3.3, 5.

Write order: Postgres local is always the write of record (see
`HybridAdminRepository`); this module is only ever called *after* a local
commit succeeds, best-effort, and its failures are caught and logged by the
caller — never propagated to the admin request. A row that fails to sync
here is retried later by the login-time self-heal (`GET /admin/me`), driven
by `PolicyRow.synced_at`.

Never issues DELETE: the `policy_writer_<schema>` Postgres role has no DELETE
grant on `access_policy` (it's meant to be append-only across every
data-proxy tenant). Grants and revokes share one mechanism: an upsert
(`POST` with `Prefer: resolution=merge-duplicates` and
`on_conflict=subject,unit_type,unit_id`) whose payload carries each row's
current `is_enabled` — `true` grants, `false` soft-revokes. Because the
filter lives in the JSON body instead of the query string, batches are split
only by serialized body size (`_UPSERT_CHUNK_BYTES`), so neither nginx's
request-line limit (the historical 414) nor its default 1MB body limit is
ever hit. A revoke upsert for a row absent on the data-proxy simply inserts
it already disabled — harmless for RLS (only `is_enabled=true` grants
access) and better self-healing than the old `PATCH`, which matched nothing.
"""

import json
from datetime import UTC, datetime

from postgrest import AsyncPostgrestClient
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


class AccessPolicySync:
    """Best-effort push of local `policy` rows into `access_policy`."""

    def __init__(self, generic_client: PostgrestClient) -> None:
        self._client: AsyncPostgrestClient = generic_client.for_schema(
            generic_client._config.schema
        )

    async def push(self, rows: list[PolicyRow]) -> list[PolicyRow]:
        """Push every row's current state to the data-proxy, best-effort.

        Grants (`is_enabled=true`) and revokes (`is_enabled=false`) share one
        mechanism: each row is upserted with its own `is_enabled`, in as few
        `POST` batches as `_UPSERT_CHUNK_BYTES` allows — never one request
        per row and never a filter built into the query string (which used to
        overflow nginx's request-line limit as a 414). Returns the subset of
        `rows` confirmed pushed; callers should leave `synced_at` unset on
        the rest so the next self-heal pass retries them.
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

        payloads = [
            {
                "subject": row.subject,
                "is_admin": row.is_admin,
                "is_enabled": row.is_enabled,
                "unit_type": row.unit_type,
                "unit_id": row.unit_id,
            }
            for row in rows
        ]

        pushed: list[PolicyRow] = []
        for chunk_rows, chunk_payloads in _upsert_chunks(rows, payloads):
            if await self._upsert(chunk_payloads):
                pushed.extend(chunk_rows)
        return pushed

    async def _upsert(self, payload: list[dict]) -> bool:
        grants = sum(1 for row in payload if row["is_enabled"])
        try:
            await (
                self._client.from_(ACCESS_POLICY_TABLE)
                .upsert(payload, on_conflict=ON_CONFLICT_COLUMNS)
                .execute()
            )
        except Exception:
            logger.exception(
                f"Falha ao sincronizar {len(payload)} linha(s) com "
                f"access_policy ({grants} grant(s), "
                f"{len(payload) - grants} revoke(s))"
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
