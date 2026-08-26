"""Tests for HybridAdminRepository's `policy` write helpers.

Runs against a real (in-memory) SQLite engine rather than mocking the ORM,
so the tests exercise actual SQL semantics (SELECT/INSERT/UPDATE) - not just
that the right Python calls were made. Only the `policy` table is created
(no `users`): SQLite doesn't enforce FKs unless `PRAGMA foreign_keys=ON` is
set, which we don't need for these tests. See `PolicyRow.id`'s
`.with_variant(Integer, "sqlite")` in `db/models.py` for why this works.

Data-proxy push (`AccessPolicySync`/`push_and_mark_synced`) is out of scope
here - it's already covered by
`data_proxy/tests/test_access_policy_sync.py`. These tests only cover the
pure local-write logic (`_replace_policy_grants`, `_set_all_policy_enabled`,
`_sync_super_admin_base_row`).
"""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.security.permissions_models import IdWithName
from src.pic.infrastructure.db.models import BASE_UNIT_ID, BASE_UNIT_TYPE, PolicyRow
from src.pic.infrastructure.repositories.hybrid_admin import HybridAdminRepository

SCHEMA = "app_pequenos_cariocas"
CPF = "12345678900"


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(PolicyRow.__table__.create)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s

    await engine.dispose()


async def _all_policy_rows(session: AsyncSession) -> list[PolicyRow]:
    result = await session.execute(select(PolicyRow))
    return list(result.scalars().all())


# ----------------------------------------------------------------------
# _replace_policy_grants
# ----------------------------------------------------------------------


async def test_replace_policy_grants_creates_new_enabled_rows(session):
    changed = await HybridAdminRepository._replace_policy_grants(
        session,
        CPF,
        {
            "id_cras_list": [
                IdWithName(id="1", nome="CRAS 1"),
                IdWithName(id="2", nome="CRAS 2"),
            ]
        },
        is_enabled=True,
    )
    await session.commit()

    assert {row.unit_id for row in changed} == {"1", "2"}
    assert all(row.is_enabled for row in changed)
    assert all(row.synced_at is None for row in changed)

    rows = await _all_policy_rows(session)
    assert {row.unit_id for row in rows} == {"1", "2"}


async def test_replace_policy_grants_dedupes_repeated_ids_in_the_same_list(session):
    """Regression test: a duplicate id within the same incoming list (e.g.
    frontend multi-select quirks) used to crash with a `uq_policy_grant`
    unique violation, because the loop only checked for duplicates against
    rows already committed in the database, not against ids seen earlier in
    the same batch."""
    changed = await HybridAdminRepository._replace_policy_grants(
        session,
        CPF,
        {
            "id_cras_list": [
                IdWithName(id="1", nome="CRAS 1"),
                IdWithName(id="1", nome="CRAS 1"),
            ]
        },
        is_enabled=True,
    )
    await session.commit()

    assert [row.unit_id for row in changed] == ["1"]
    rows = await _all_policy_rows(session)
    assert [row.unit_id for row in rows] == ["1"]


async def test_replace_policy_grants_is_idempotent(session):
    id_lists = {"id_cras_list": [IdWithName(id="1", nome="CRAS 1")]}
    await HybridAdminRepository._replace_policy_grants(
        session, CPF, id_lists, is_enabled=True
    )
    await session.commit()

    changed = await HybridAdminRepository._replace_policy_grants(
        session, CPF, id_lists, is_enabled=True
    )
    await session.commit()

    assert changed == []
    assert len(await _all_policy_rows(session)) == 1


async def test_replace_policy_grants_soft_disables_removed_units_without_deleting(
    session,
):
    await HybridAdminRepository._replace_policy_grants(
        session,
        CPF,
        {"id_cras_list": [IdWithName(id="1", nome="a"), IdWithName(id="2", nome="b")]},
        is_enabled=True,
    )
    await session.commit()

    changed = await HybridAdminRepository._replace_policy_grants(
        session, CPF, {"id_cras_list": [IdWithName(id="1", nome="a")]}, is_enabled=True
    )
    await session.commit()

    rows = await _all_policy_rows(session)
    assert len(rows) == 2  # row for unit_id=2 still exists, never deleted
    disabled = next(row for row in rows if row.unit_id == "2")
    assert disabled.is_enabled is False
    assert disabled.synced_at is None
    assert disabled in changed


async def test_replace_policy_grants_re_enables_a_previously_revoked_unit(session):
    await HybridAdminRepository._replace_policy_grants(
        session, CPF, {"id_cras_list": [IdWithName(id="1", nome="a")]}, is_enabled=True
    )
    await session.commit()
    await HybridAdminRepository._replace_policy_grants(
        session, CPF, {"id_cras_list": []}, is_enabled=True
    )
    await session.commit()

    rows = await _all_policy_rows(session)
    assert rows[0].is_enabled is False

    changed = await HybridAdminRepository._replace_policy_grants(
        session, CPF, {"id_cras_list": [IdWithName(id="1", nome="a")]}, is_enabled=True
    )
    await session.commit()

    rows = await _all_policy_rows(session)
    assert len(rows) == 1  # re-enabled the same row, didn't insert a new one
    assert rows[0].is_enabled is True
    assert changed == [rows[0]]


async def test_replace_policy_grants_leaves_untouched_unit_types_alone(session):
    await HybridAdminRepository._replace_policy_grants(
        session, CPF, {"id_cras_list": [IdWithName(id="1", nome="a")]}, is_enabled=True
    )
    await session.commit()

    # id_escola_list not provided at all -> nothing for id_cras_list should change.
    changed = await HybridAdminRepository._replace_policy_grants(
        session,
        CPF,
        {"id_escola_list": [IdWithName(id="9", nome="x")]},
        is_enabled=True,
    )
    await session.commit()

    assert {row.unit_type for row in changed} == {"escola"}
    rows = await _all_policy_rows(session)
    assert len(rows) == 2


# ----------------------------------------------------------------------
# _set_all_policy_enabled
# ----------------------------------------------------------------------


async def test_set_all_policy_enabled_flips_only_rows_that_differ(session):
    await HybridAdminRepository._replace_policy_grants(
        session,
        CPF,
        {
            "id_cras_list": [IdWithName(id="1", nome="a")],
            "id_escola_list": [IdWithName(id="2", nome="b")],
        },
        is_enabled=True,
    )
    await session.commit()

    changed = await HybridAdminRepository._set_all_policy_enabled(
        session, CPF, enabled=False
    )
    await session.commit()

    assert len(changed) == 2
    rows = await _all_policy_rows(session)
    assert all(row.is_enabled is False for row in rows)
    assert all(row.synced_at is None for row in rows)

    # Calling again with the same value is a no-op.
    changed_again = await HybridAdminRepository._set_all_policy_enabled(
        session, CPF, enabled=False
    )
    assert changed_again == []


# ----------------------------------------------------------------------
# _sync_super_admin_base_row
# ----------------------------------------------------------------------


async def test_sync_super_admin_base_row_creates_sentinel_row_when_granted(session):
    row = await HybridAdminRepository._sync_super_admin_base_row(
        session, CPF, is_super_admin=True, active=True
    )
    await session.commit()

    assert row is not None
    assert row.unit_type == BASE_UNIT_TYPE
    assert row.unit_id == BASE_UNIT_ID
    assert row.is_admin is True
    assert row.is_enabled is True


async def test_sync_super_admin_base_row_is_noop_when_never_granted(session):
    row = await HybridAdminRepository._sync_super_admin_base_row(
        session, CPF, is_super_admin=False, active=True
    )
    assert row is None
    assert await _all_policy_rows(session) == []


async def test_sync_super_admin_base_row_disables_instead_of_deleting(session):
    await HybridAdminRepository._sync_super_admin_base_row(
        session, CPF, is_super_admin=True, active=True
    )
    await session.commit()

    row = await HybridAdminRepository._sync_super_admin_base_row(
        session, CPF, is_super_admin=False, active=True
    )
    await session.commit()

    assert row is not None
    assert row.is_enabled is False
    rows = await _all_policy_rows(session)
    assert len(rows) == 1  # still there, just disabled


async def test_sync_super_admin_base_row_re_grant_reuses_the_same_row(session):
    await HybridAdminRepository._sync_super_admin_base_row(
        session, CPF, is_super_admin=True, active=True
    )
    await session.commit()
    await HybridAdminRepository._sync_super_admin_base_row(
        session, CPF, is_super_admin=False, active=True
    )
    await session.commit()

    row = await HybridAdminRepository._sync_super_admin_base_row(
        session, CPF, is_super_admin=True, active=True
    )
    await session.commit()

    assert row is not None
    assert row.is_enabled is True
    assert len(await _all_policy_rows(session)) == 1


async def test_sync_super_admin_base_row_stays_disabled_when_inactive(session):
    """A request that grants is_super_admin=True and active=False at the
    same time (both fields live on the same edit form) must never leave
    the RLS-bypass row enabled."""
    row = await HybridAdminRepository._sync_super_admin_base_row(
        session, CPF, is_super_admin=True, active=False
    )
    await session.commit()

    assert row is not None
    assert row.is_enabled is False
