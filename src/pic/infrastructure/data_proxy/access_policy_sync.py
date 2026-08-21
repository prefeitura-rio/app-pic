"""Sync of local `policy` rows into the data-proxy's `rls.access_policy`.

Domain-specific on top of `postgrest_client` (which knows nothing about
`access_policy`'s columns or the `rls` schema). See plan.md sections 3.3, 5.

Write order: Postgres local is always the write of record (see
`HybridAdminRepository`); this module is only ever called *after* a local
commit succeeds, best-effort, and its failures are caught and logged by the
caller — never propagated to the admin request. A row that fails to sync
here is retried later by the login-time self-heal (`GET /admin/me`), driven
by `PolicyRow.synced_at`.

Never issues DELETE: the `policy_writer_<schema>` Postgres role has no DELETE
grant on `access_policy` (it's meant to be append-only across every
data-proxy tenant). Revoking a grant is always `PATCH is_enabled=false`.
"""

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

# `access_policy` lives in a schema of its own, shared by every data-proxy
# tenant — distinct from the app's data schema (`app_pequenos_cariocas`,
# config.PostgrestClientConfig.schema). Requires `Content-Profile: rls`.
RLS_SCHEMA = "rls"
ACCESS_POLICY_TABLE = "access_policy"

# Unique constraint on `rls.access_policy` (and on the local mirror `policy`)
# — see plan.md section 3.3.
ON_CONFLICT_COLUMNS = "schema,subject,unit_type,unit_id"


class AccessPolicySync:
    """Best-effort push of local `policy` rows into `rls.access_policy`."""

    def __init__(self, generic_client: PostgrestClient) -> None:
        self._client: AsyncPostgrestClient = generic_client.for_schema(RLS_SCHEMA)

    async def push(self, rows: list[PolicyRow]) -> list[PolicyRow]:
        """Push every row's current state to the data-proxy, best-effort.

        Enabled rows are upserted (grant) as a single batch; disabled rows
        are soft-revoked (`is_enabled=false`) one at a time — never deleted.
        Returns the subset of `rows` that were confirmed pushed; callers
        should leave `synced_at` unset on the rest so the next self-heal
        pass retries them.
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

        to_grant = [row for row in rows if row.is_enabled]
        to_revoke = [row for row in rows if not row.is_enabled]

        pushed: list[PolicyRow] = []
        if to_grant and await self._grant(to_grant):
            pushed.extend(to_grant)
        for row in to_revoke:
            if await self._revoke(row):
                pushed.append(row)
        return pushed

    async def _grant(self, rows: list[PolicyRow]) -> bool:
        payload = [
            {
                "schema": row.schema,
                "subject": row.subject,
                "is_admin": row.is_admin,
                "is_enabled": True,
                "unit_type": row.unit_type,
                "unit_id": row.unit_id,
            }
            for row in rows
        ]
        try:
            await (
                self._client.from_(ACCESS_POLICY_TABLE)
                .upsert(payload, on_conflict=ON_CONFLICT_COLUMNS)
                .execute()
            )
        except Exception:
            logger.exception(
                f"Falha ao sincronizar {len(rows)} grant(s) com rls.access_policy"
            )
            return False
        return True

    async def _revoke(self, row: PolicyRow) -> bool:
        try:
            await (
                self._client.from_(ACCESS_POLICY_TABLE)
                .update({"is_enabled": False})
                .eq("schema", row.schema)
                .eq("subject", row.subject)
                .eq("unit_type", row.unit_type)
                .eq("unit_id", row.unit_id)
                .execute()
            )
        except Exception:
            logger.exception(
                f"Falha ao revogar grant em rls.access_policy "
                f"(subject={row.subject}, unit_type={row.unit_type}, unit_id={row.unit_id})"
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
        logger.exception("Falha ao inicializar sync com rls.access_policy")
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
