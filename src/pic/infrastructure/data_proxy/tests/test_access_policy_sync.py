import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from urllib.parse import quote_plus

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


def confirmed_revoke_row(**overrides) -> PolicyRow:
    """A revoke whose DELETE was already confirmed on the data-proxy
    (`synced_at >= updated_at`) — must be skipped by `push`."""
    stamp = datetime(2026, 1, 1, tzinfo=UTC)
    return revoke_row(synced_at=stamp, updated_at=stamp, **overrides)


def fake_data_proxy(*, post_status: int = 201, delete_status: int = 204):
    """Fakes Keycloak + the data-proxy's access_policy endpoint. Records
    every non-token request."""
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "keycloak.example":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})

        requests.append(request)
        if request.method == "POST":
            return httpx.Response(post_status, json=[])
        if request.method == "DELETE":
            return httpx.Response(delete_status)
        raise AssertionError(f"unexpected method {request.method}")

    handler.requests = requests  # type: ignore[attr-defined]
    return handler


def make_sync(handler) -> AccessPolicySync:
    client = PostgrestClient(CONFIG, transport=httpx.MockTransport(handler))
    return AccessPolicySync(client)


def delete_filter(req: httpx.Request) -> dict[str, str]:
    """Extract the (subject, unit_type, unit_id) filters of a DELETE."""
    return {
        name: req.url.params.get(name)
        for name in ("subject", "unit_type", "unit_id")
    }


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
    assert "is_enabled" not in payload[0]


async def test_revoke_deletes_row_filtered_by_pk():
    """`access_policy` no longer has `is_enabled` — a revoke is a hard
    DELETE filtered by subject/unit_type/unit_id, not a soft upsert. The
    DELETE uses `return=representation`: the data-proxy hangs on the
    minimal/204 path (observed in staging)."""
    handler = fake_data_proxy()
    sync = make_sync(handler)
    row = revoke_row(unit_id="42")

    pushed = await sync.push([row])

    assert pushed == [row]
    sent = handler.requests[0]
    assert sent.method == "DELETE"
    assert sent.headers["content-profile"] == "app_pequenos_cariocas"
    assert "return=representation" in sent.headers["prefer"]
    assert delete_filter(sent) == {
        "subject": "eq.12345678900",
        "unit_type": "eq.cras",
        "unit_id": "in.(42)",
    }


async def test_push_mixes_grants_and_revokes_into_post_and_delete():
    """Grants travel in one upsert POST; revokes become DELETEs grouped by
    (subject, unit_type)."""
    handler = fake_data_proxy()
    sync = make_sync(handler)
    g1 = grant_row(id=1, unit_id="1", unit_type="cras")
    g2 = grant_row(id=2, unit_id="2", unit_type="cras")
    r = revoke_row(id=3, unit_id="2", unit_type="escola")

    pushed = await sync.push([g1, g2, r])

    assert set(pushed) == {g1, g2, r}
    assert len(handler.requests) == 2
    post = next(req for req in handler.requests if req.method == "POST")
    delete = next(req for req in handler.requests if req.method == "DELETE")
    payload = json.loads(post.content)
    assert {p["unit_id"] for p in payload} == {"1", "2"}
    assert all("is_enabled" not in p for p in payload)
    assert delete_filter(delete) == {
        "subject": "eq.12345678900",
        "unit_type": "eq.escola",
        "unit_id": "in.(2)",
    }


async def test_grant_push_chunks_by_body_budget(monkeypatch):
    """Grant batches are split by serialized body size (never by row count
    or unit_type), keeping every POST under the data-proxy's body limit."""
    monkeypatch.setattr(access_policy_sync, "_UPSERT_CHUNK_BYTES", 200)
    handler = fake_data_proxy()
    sync = make_sync(handler)
    rows = [grant_row(id=i, unit_id=str(i)) for i in range(1, 6)]

    pushed = await sync.push(rows)

    assert set(pushed) == set(rows)
    # ~82 bytes of JSON per row -> two rows per 200-byte chunk.
    assert len(handler.requests) == 3
    for req in handler.requests:
        assert req.method == "POST"
        body = json.loads(req.content)
        assert sum(len(json.dumps(row)) for row in body) <= 200
    unit_ids = {
        p["unit_id"] for req in handler.requests for p in json.loads(req.content)
    }
    assert unit_ids == {"1", "2", "3", "4", "5"}


async def test_revoke_delete_chunks_by_url_budget(monkeypatch):
    """Revoke DELETEs are chunked by URL-encoded `in.(...)` size, so long
    unit ids (e.g. school codes) never overflow nginx's request line."""
    monkeypatch.setattr(access_policy_sync, "_DELETE_URL_CHUNK_BYTES", 40)
    handler = fake_data_proxy()
    sync = make_sync(handler)
    rows = [
        revoke_row(id=i, unit_id=f"ESCOLA_{'X' * 20}_{i}")
        for i in range(1, 4)
    ]

    pushed = await sync.push(rows)

    assert set(pushed) == set(rows)
    # Each id is ~29 encoded bytes + comma > 40-byte budget -> one request
    # per id.
    assert len(handler.requests) == 3
    ids: set[str] = set()
    for req in handler.requests:
        assert req.method == "DELETE"
        unit_id = req.url.params.get("unit_id")
        assert unit_id.startswith("in.(")
        inner = unit_id[4:-1]
        encoded_len = sum(len(quote_plus(part)) for part in inner.split(","))
        commas = inner.count(",")
        assert encoded_len + commas <= 40
        ids.update(inner.split(","))
    assert ids == {f"ESCOLA_{'X' * 20}_{i}" for i in range(1, 4)}


async def test_revoke_delete_groups_by_subject_and_unit_type():
    """Revokes sharing (subject, unit_type) travel in one DELETE with a
    joined `unit_id=in.(...)`."""
    handler = fake_data_proxy()
    sync = make_sync(handler)
    r1 = revoke_row(id=1, unit_id="1", unit_type="escola")
    r2 = revoke_row(id=2, unit_id="2", unit_type="escola")
    r3 = revoke_row(id=3, unit_id="3", unit_type="cras")

    pushed = await sync.push([r1, r2, r3])

    assert set(pushed) == {r1, r2, r3}
    assert len(handler.requests) == 2
    filters = sorted(
        (delete_filter(req)["unit_type"], delete_filter(req)["unit_id"])
        for req in handler.requests
    )
    assert filters == [
        ("eq.cras", "in.(3)"),
        ("eq.escola", "in.(1,2)"),
    ]


async def test_push_skips_confirmed_revokes():
    """A revoke already confirmed on the data-proxy (`synced_at >=
    updated_at`) is skipped — a forced self-heal must not re-DELETE every
    login."""
    handler = fake_data_proxy()
    sync = make_sync(handler)
    row = confirmed_revoke_row(unit_id="42")

    pushed = await sync.push([row])

    assert pushed == []
    assert handler.requests == []


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


async def test_grant_chunk_failure_pushes_only_successful_chunks(monkeypatch):
    """One failed POST chunk leaves only its own rows unsynced; the
    remaining chunks still complete (the next self-heal retries the failed
    ones)."""
    monkeypatch.setattr(access_policy_sync, "_UPSERT_CHUNK_BYTES", 200)
    statuses = iter([500, 201, 201])

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "keycloak.example":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        return httpx.Response(next(statuses), json=[])

    sync = make_sync(handler)
    rows = [grant_row(id=i, unit_id=str(i)) for i in range(1, 6)]

    pushed = await sync.push(rows)

    # First POST (rows 1-2) failed; rows 3-5 landed.
    assert {r.id for r in pushed} == {3, 4, 5}


async def test_revoke_chunk_failure_leaves_its_rows_unsynced(monkeypatch):
    """A failed DELETE chunk leaves only its own rows unsynced; the other
    chunks still complete."""
    monkeypatch.setattr(access_policy_sync, "_DELETE_URL_CHUNK_BYTES", 40)
    statuses = iter([500, 204, 204])

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "keycloak.example":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        return httpx.Response(next(statuses))

    sync = make_sync(handler)
    rows = [
        revoke_row(id=i, unit_id=f"ESCOLA_{'X' * 20}_{i}")
        for i in range(1, 4)
    ]

    pushed = await sync.push(rows)

    # First DELETE (row 1) failed; rows 2-3 landed.
    assert {r.id for r in pushed} == {2, 3}


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
