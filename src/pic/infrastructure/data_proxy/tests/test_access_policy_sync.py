import json
from contextlib import asynccontextmanager

import httpx

from src.pic.infrastructure.data_proxy import access_policy_sync
from src.pic.infrastructure.data_proxy.access_policy_sync import (
    AccessPolicySync,
    push_and_mark_synced,
)
from src.pic.infrastructure.db.models import PolicyRow
from src.pic.infrastructure.postgrest_client.client import PostgrestClient
from src.pic.infrastructure.postgrest_client.config import PostgrestClientConfig

CONFIG = PostgrestClientConfig(
    base_url="https://data-proxy.example/",
    schema="app_pequenos_cariocas",
    token_url="https://keycloak.example/token",
    client_id="policy-writer",
    client_secret="secret",
)


def grant_row(**overrides) -> PolicyRow:
    defaults = {
        "id": 1,
        "schema": "app_pequenos_cariocas",
        "subject": "12345678900",
        "is_admin": False,
        "is_enabled": True,
        "unit_type": "cras",
        "unit_id": "1",
    }
    defaults.update(overrides)
    return PolicyRow(**defaults)


def revoke_row(**overrides) -> PolicyRow:
    return grant_row(is_enabled=False, **overrides)


def fake_data_proxy(*, grant_status: int = 201, revoke_status: int = 200):
    """Fakes Keycloak + the data-proxy's access_policy endpoint. Records
    every non-token request."""
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "keycloak.example":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})

        requests.append(request)
        if request.method == "POST":
            return httpx.Response(grant_status, json=[])
        if request.method == "PATCH":
            return httpx.Response(revoke_status, json=[])
        raise AssertionError(f"unexpected method {request.method}")

    handler.requests = requests  # type: ignore[attr-defined]
    return handler


def make_sync(handler) -> AccessPolicySync:
    client = PostgrestClient(CONFIG, transport=httpx.MockTransport(handler))
    return AccessPolicySync(client)


async def test_grant_upserts_with_merge_duplicates_and_app_schema_profile():
    handler = fake_data_proxy()
    sync = make_sync(handler)
    row = grant_row()

    pushed = await sync.push([row])

    assert pushed == [row]
    sent = handler.requests[0]
    assert sent.method == "POST"
    assert sent.url.path == "/access_policy"
    assert sent.headers["content-profile"] == "app_pequenos_cariocas"
    assert "resolution=merge-duplicates" in sent.headers["prefer"]
    assert sent.url.params["on_conflict"] == "subject,unit_type,unit_id"
    payload = json.loads(sent.content)
    assert "schema" not in payload[0]


async def test_revoke_patches_is_enabled_false_filtered_by_row():
    handler = fake_data_proxy()
    sync = make_sync(handler)
    row = revoke_row(unit_id="42")

    pushed = await sync.push([row])

    assert pushed == [row]
    sent = handler.requests[0]
    assert sent.method == "PATCH"
    assert sent.headers["content-profile"] == "app_pequenos_cariocas"
    assert sent.url.params["unit_id"] == "in.(42)"
    assert sent.url.params["subject"] == "eq.12345678900"
    assert "schema" not in sent.url.params


async def test_revoke_batches_same_unit_type_into_a_single_patch():
    """Revoking many units of the same (subject, unit_type) should
    cost one PATCH request, not one per unit_id."""
    handler = fake_data_proxy()
    sync = make_sync(handler)
    rows = [revoke_row(id=i, unit_id=str(i)) for i in range(1, 6)]

    pushed = await sync.push(rows)

    assert set(pushed) == set(rows)
    assert len(handler.requests) == 1
    sent = handler.requests[0]
    assert sent.method == "PATCH"
    assert sent.url.params["unit_id"] == "in.(1,2,3,4,5)"


async def test_revoke_groups_by_unit_type_into_separate_patches():
    """Different unit_types can't share one `unit_id=in.(...)` filter
    (it would revoke the cross-product), so each unit_type gets its own
    PATCH — still far fewer requests than one per row."""
    handler = fake_data_proxy()
    sync = make_sync(handler)
    cras = [revoke_row(id=1, unit_type="cras", unit_id="1")]
    escola = [
        revoke_row(id=2, unit_type="escola", unit_id="9"),
        revoke_row(id=3, unit_type="escola", unit_id="10"),
    ]

    pushed = await sync.push(cras + escola)

    assert set(pushed) == set(cras + escola)
    assert len(handler.requests) == 2
    unit_id_filters = {req.url.params["unit_id"] for req in handler.requests}
    assert unit_id_filters == {"in.(1)", "in.(9,10)"}


async def test_push_mixes_grants_and_revokes_in_one_call():
    handler = fake_data_proxy()
    sync = make_sync(handler)
    g = grant_row(id=1, unit_id="1")
    r = revoke_row(id=2, unit_id="2")

    pushed = await sync.push([g, r])

    assert set(pushed) == {g, r}
    methods = {req.method for req in handler.requests}
    assert methods == {"POST", "PATCH"}


async def test_push_returns_empty_list_when_no_rows():
    sync = make_sync(fake_data_proxy())
    assert await sync.push([]) == []


async def test_push_dedupes_rows_sharing_the_same_primary_key():
    """Regression test: the same underlying `policy` row (same `id`) ending
    up twice in `rows` — e.g. because two local mutations touched it in one
    write — used to be sent as two entries in the same upsert batch, which
    Postgres rejects with "ON CONFLICT DO UPDATE command cannot affect row
    a second time"."""
    handler = fake_data_proxy()
    sync = make_sync(handler)
    stale = grant_row(id=1, unit_id="1")
    fresh = grant_row(id=1, unit_id="1")  # same row, appended a second time

    pushed = await sync.push([stale, fresh])

    assert pushed == [fresh]
    assert len(handler.requests) == 1
    payload = json.loads(handler.requests[0].content)
    assert len(payload) == 1


async def test_grant_failure_does_not_block_revoke_success():
    handler = fake_data_proxy(grant_status=500)
    sync = make_sync(handler)
    g = grant_row(id=1)
    r = revoke_row(id=2)

    pushed = await sync.push([g, r])

    assert pushed == [r]


async def test_revoke_failure_does_not_block_grant_success():
    handler = fake_data_proxy(revoke_status=500)
    sync = make_sync(handler)
    g = grant_row(id=1)
    r = revoke_row(id=2)

    pushed = await sync.push([g, r])

    assert pushed == [g]


async def _fake_get_postgrest_client():
    return object()


class _FakeSession:
    def __init__(self, log: list) -> None:
        self._log = log

    async def execute(self, stmt) -> None:
        self._log.append(stmt)

    async def commit(self) -> None:
        pass


class _FakeSyncer:
    """Stub standing in for an `AccessPolicySync` instance."""

    def __init__(self, expected_rows: list[PolicyRow], result: list[PolicyRow]) -> None:
        self._expected_rows = expected_rows
        self._result = result

    async def push(self, rows: list[PolicyRow]) -> list[PolicyRow]:
        assert rows == self._expected_rows
        return self._result


def _fake_access_policy_sync_factory(expected_rows, result):
    """Returns a stand-in for the `AccessPolicySync` class constructor, so
    `push_and_mark_synced` tests don't need a real `PostgrestClient`."""
    return lambda generic_client: _FakeSyncer(expected_rows, result)


async def test_push_and_mark_synced_stamps_only_the_rows_that_succeeded(monkeypatch):
    g = grant_row(id=1)
    r = revoke_row(id=2)

    monkeypatch.setattr(
        access_policy_sync,
        "AccessPolicySync",
        _fake_access_policy_sync_factory([g, r], [g]),
    )
    monkeypatch.setattr(
        access_policy_sync, "get_postgrest_client", _fake_get_postgrest_client
    )

    executed: list = []

    @asynccontextmanager
    async def fake_get_session():
        yield _FakeSession(executed)

    monkeypatch.setattr(access_policy_sync, "get_session", fake_get_session)

    await push_and_mark_synced([g, r])

    assert len(executed) == 1
    sql = str(executed[0].compile(compile_kwargs={"literal_binds": True}))
    assert "policy.id IN (1)" in sql


async def test_push_and_mark_synced_does_not_bump_updated_at(monkeypatch):
    """Regression test: `updated_at` has `onupdate=func.now()`, which
    SQLAlchemy injects automatically into any UPDATE that doesn't set it
    explicitly. If this statement doesn't pin `updated_at` to itself, the
    row's `updated_at` ends up (milliseconds) *after* the `synced_at` value
    being stamped here, making the row look stale again immediately and get
    re-pushed on every subsequent self-heal call, forever."""
    g = grant_row(id=1)

    monkeypatch.setattr(
        access_policy_sync,
        "AccessPolicySync",
        _fake_access_policy_sync_factory([g], [g]),
    )
    monkeypatch.setattr(
        access_policy_sync, "get_postgrest_client", _fake_get_postgrest_client
    )

    executed: list = []

    @asynccontextmanager
    async def fake_get_session():
        yield _FakeSession(executed)

    monkeypatch.setattr(access_policy_sync, "get_session", fake_get_session)

    await push_and_mark_synced([g])

    assert len(executed) == 1
    sql = str(executed[0].compile(compile_kwargs={"literal_binds": True}))
    # Pinned to the column itself rather than left for the
    # `onupdate=func.now()` default to fill in a fresh timestamp.
    assert "updated_at=policy.updated_at" in sql


async def test_push_and_mark_synced_is_a_noop_when_nothing_pushed(monkeypatch):
    row = grant_row()
    monkeypatch.setattr(
        access_policy_sync,
        "AccessPolicySync",
        _fake_access_policy_sync_factory([row], []),
    )
    monkeypatch.setattr(
        access_policy_sync, "get_postgrest_client", _fake_get_postgrest_client
    )

    called = False

    @asynccontextmanager
    async def fake_get_session():
        nonlocal called
        called = True
        yield _FakeSession([])

    monkeypatch.setattr(access_policy_sync, "get_session", fake_get_session)

    await push_and_mark_synced([row])

    assert called is False


async def test_push_and_mark_synced_swallows_client_init_errors(monkeypatch):
    async def boom():
        raise RuntimeError("data-proxy client unavailable")

    monkeypatch.setattr(access_policy_sync, "get_postgrest_client", boom)

    # Should not raise.
    await push_and_mark_synced([grant_row()])
