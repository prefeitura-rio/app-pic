"""Tests for HybridAdminRepository.

Runs against a real (in-memory) SQLite engine rather than mocking the ORM,
so the write-helper tests exercise actual SQL semantics (SELECT/INSERT/
UPDATE) - not just that the right Python calls were made. Only the `policy`
table is created (no `users`): SQLite doesn't enforce FKs unless
`PRAGMA foreign_keys=ON` is set, which we don't need for these tests. See
`PolicyRow.id`'s `.with_variant(Integer, "sqlite")` in `db/models.py` for
why this works.

Read-path tests (unit catalog / governance df / fetch_user_record /
find_paginated_users) use a fake PostgREST transport and a fake session
(no real Postgres/BigQuery).

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


# ----------------------------------------------------------------------
# fetch_unit_options (unit catalog via PostgREST grouped aggregates)
# ----------------------------------------------------------------------


def _make_catalog_repo(
    rows_by_select: dict[str, list[dict]],
    redis_client=None,
) -> tuple[HybridAdminRepository, list]:
    """Repo with a fake PostgREST transport answering catalog queries."""
    import httpx

    from src.pic.infrastructure.postgrest_client.client import PostgrestClient
    from src.pic.infrastructure.postgrest_client.config import PostgrestClientConfig

    config = PostgrestClientConfig(
        base_url="https://data-proxy.example/",
        schema="app_pequenos_cariocas",
        token_url="https://keycloak.example/token",
        client_id="pic-client",
        client_secret="pic-secret",
    )
    requests: list = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "keycloak.example":
            return httpx.Response(
                200, json={"access_token": "test-token", "expires_in": 3600}
            )
        requests.append(request)
        select = request.url.params.get("select", "")
        rows = next(
            (
                r
                for key, r in rows_by_select.items()
                if select.startswith(key)
            ),
            [],
        )
        return httpx.Response(200, json=rows, request=request)

    client = PostgrestClient(config, transport=httpx.MockTransport(handler))
    return HybridAdminRepository(client, redis_client=redis_client), requests


async def test_fetch_unit_options_groups_and_filters_nulls():
    repo, requests = _make_catalog_repo(
        {
            "id_cras,nome_cras,count()": [
                {"id_cras": "1", "nome_cras": "CRAS Centro", "count": 3},
                {"id_cras": "2", "nome_cras": "CRAS Sul", "count": 1},
                {"id_cras": None, "nome_cras": "ignored", "count": 5},
            ],
        }
    )
    options = await repo.fetch_unit_options("cras", user_token="jwt")

    assert [(o.id, o.nome) for o in options] == [
        ("1", "CRAS Centro"),
        ("2", "CRAS Sul"),
    ]
    # Query shape: grouped aggregate + not.is.null on the wide table
    req = requests[0]
    assert req.url.path.endswith("/endpoint_participante_protocolos_wide")
    assert "count()" in req.url.params["select"]
    assert req.url.params["id_cras"] == "not.is.null"


async def test_fetch_unit_options_cre_uses_nome_cre():
    repo, _ = _make_catalog_repo(
        {
            "id_cre,nome_cre,count()": [
                {"id_cre": "10", "nome_cre": "1a CRE", "count": 1},
                {"id_cre": "2", "nome_cre": None, "count": 2},
            ]
        }
    )
    options = await repo.fetch_unit_options("cre", user_token="jwt")

    # Real nome_cre wins; NULL falls back to the id itself.
    assert [(o.id, o.nome) for o in options] == [("10", "1a CRE"), ("2", "2")]


async def test_fetch_unit_options_unknown_type_raises():
    repo, _ = _make_catalog_repo({})
    import pytest

    with pytest.raises(ValueError):
        await repo.fetch_unit_options("nao_existe", user_token="jwt")


async def test_fetch_unit_options_uses_redis_cache():
    import json as json_lib
    from unittest.mock import AsyncMock, MagicMock

    repo, requests = _make_catalog_repo(
        {"id_cras,nome_cras,count()": [{"id_cras": "1", "nome_cras": "CRAS Centro", "count": 3}]}
    )

    # Cache MISS
    redis = MagicMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    repo._redis = redis
    options = await repo.fetch_unit_options("cras", user_token="jwt")
    assert len(options) == 1
    assert len(requests) == 1
    redis.set.assert_awaited_once()

    # Cache HIT (second call skips PostgREST)
    redis.get = AsyncMock(
        return_value=json_lib.dumps([{"id": "9", "nome": "Cached"}])
    )
    options = await repo.fetch_unit_options("cras", user_token="jwt")
    assert [(o.id, o.nome) for o in options] == [("9", "Cached")]
    assert len(requests) == 1  # no new HTTP request


# ----------------------------------------------------------------------
# fetch_governance_df (raw) / fetch_user_record (raw, zero PostgREST)
# ----------------------------------------------------------------------


def _make_user(**overrides) -> object:
    from datetime import UTC, datetime

    from src.pic.infrastructure.db.models import User

    defaults = {
        "cpf": "11111111111",
        "email": None,
        "nome": "Joao",
        "ocupacao": None,
        "secretaria": None,
        "secretarias_acesso": [],
        "is_admin": False,
        "is_super_admin": False,
        "active": True,
        "notes": None,
        "created_by": "system",
        "updated_by": None,
        "created_at": datetime(2025, 1, 1, tzinfo=UTC),
        "updated_at": datetime(2025, 1, 1, tzinfo=UTC),
    }
    defaults.update(overrides)
    return User(**defaults)


class _FakeUsersResult:
    def __init__(self, users: list[object]):
        self._users = users

    def scalars(self):
        return self

    def all(self):
        return self._users

    def scalar_one_or_none(self):
        return self._users[0] if self._users else None


class _FakePolicyResult:
    def __init__(self, rows: list[tuple]):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, users: list[object], policy_rows: list[tuple]):
        self._users = users
        self._policy_rows = policy_rows

    async def execute(self, stmt):
        compiled = str(stmt)
        if "FROM users" in compiled:
            return _FakeUsersResult(self._users)
        if "FROM policy" in compiled:
            return _FakePolicyResult(self._policy_rows)
        raise AssertionError(f"Unexpected statement: {compiled}")


@pytest.fixture
def patch_get_session(monkeypatch):
    """Patch the module-level `get_session` with a fake returning `session`."""

    def _patch(session):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _fake_get_session():
            yield session

        monkeypatch.setattr(
            "src.pic.infrastructure.repositories.hybrid_admin.get_session",
            _fake_get_session,
        )

    return _patch


async def test_fetch_governance_df_is_raw_and_zero_postgrest(patch_get_session):
    patch_get_session(
        _FakeSession(
            users=[_make_user(cpf=CPF)],
            policy_rows=[(CPF, "cras", "1")],
        )
    )
    repo, requests = _make_catalog_repo({})

    df, _, _ = await repo.fetch_governance_df()

    assert requests == []
    row = df.to_dicts()[0]
    assert row["id_cras_list"] == [{"id": "1", "nome": "1"}]  # raw id-as-name


async def test_find_paginated_users_keeps_raw_ids_and_zero_postgrest(
    patch_get_session,
):
    patch_get_session(
        _FakeSession(
            users=[_make_user(cpf=CPF)],
            policy_rows=[(CPF, "cras", "1")],
        )
    )
    repo, requests = _make_catalog_repo({})

    df_result, _, _ = await repo.find_paginated_users(
        filters_dict={},
        page=1,
        page_size=10,
        search=None,
        filter_columns_config=None,
    )

    row = df_result.to_dicts()[0]
    # Raw id-as-name (names are resolved lazily by the dropdown options UI-side)
    assert row["id_cras_list"] == [{"id": "1", "nome": "1"}]
    assert requests == []


async def test_fetch_user_record_returns_raw_ids_without_postgrest(
    patch_get_session,
):
    patch_get_session(
        _FakeSession(
            users=[_make_user(cpf=CPF)],
            policy_rows=[("cras", "1"), ("cre", "10")],
        )
    )
    repo, requests = _make_catalog_repo({})

    row = await repo.fetch_user_record(CPF, user_token="jwt")

    assert row is not None
    assert row["id_cras_list"] == [{"id": "1", "nome": "1"}]
    assert row["id_cre_list"] == [{"id": "10", "nome": "10"}]
    assert requests == []  # zero PostgREST calls, regardless of grant count


async def test_fetch_user_record_returns_none_for_unknown_cpf(patch_get_session):
    patch_get_session(_FakeSession(users=[], policy_rows=[]))
    repo, _ = _make_catalog_repo({})

    row = await repo.fetch_user_record("00000000000", user_token="jwt")

    assert row is None
