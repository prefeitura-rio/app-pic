import asyncio

import httpx
import pytest

from src.pic.infrastructure.postgrest_client.auth import ClientCredentialsAuth
from src.pic.infrastructure.postgrest_client.config import PostgrestClientConfig

CONFIG = PostgrestClientConfig(
    base_url="https://data-proxy.example/",
    schema="app_pequenos_cariocas",
    token_url="https://keycloak.example/realms/pic/protocol/openid-connect/token",
    client_id="pic-client",
    client_secret="pic-secret",
)


def token_endpoint_handler(token: str = "fake-token", *, expires_in: int | None = 3600):
    """Fakes Keycloak's client_credentials grant and records every call."""
    calls: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        body: dict = {"access_token": token}
        if expires_in is not None:
            body["expires_in"] = expires_in
        return httpx.Response(200, json=body)

    handler.calls = calls  # type: ignore[attr-defined]
    return handler


async def test_on_request_fetches_and_attaches_bearer_token():
    handler = token_endpoint_handler(token="abc123")
    auth = ClientCredentialsAuth(CONFIG, transport=httpx.MockTransport(handler))

    request = httpx.Request("GET", "https://data-proxy.example/participants")
    await auth.on_request(request)

    assert request.headers["Authorization"] == "Bearer abc123"
    assert len(handler.calls) == 1

    await auth.aclose()


async def test_on_request_sends_client_credentials_grant():
    handler = token_endpoint_handler()
    auth = ClientCredentialsAuth(CONFIG, transport=httpx.MockTransport(handler))

    await auth.on_request(httpx.Request("GET", "https://data-proxy.example/x"))

    sent = handler.calls[0]
    form = dict(httpx.QueryParams(sent.read().decode()))
    assert form == {
        "grant_type": "client_credentials",
        "client_id": "pic-client",
        "client_secret": "pic-secret",
    }

    await auth.aclose()


async def test_token_is_cached_across_requests():
    handler = token_endpoint_handler(token="cached-token")
    auth = ClientCredentialsAuth(CONFIG, transport=httpx.MockTransport(handler))

    await auth.on_request(httpx.Request("GET", "https://data-proxy.example/a"))
    await auth.on_request(httpx.Request("GET", "https://data-proxy.example/b"))
    await auth.on_request(httpx.Request("GET", "https://data-proxy.example/c"))

    assert len(handler.calls) == 1

    await auth.aclose()


async def test_concurrent_cold_start_fetches_token_once():
    handler = token_endpoint_handler()
    auth = ClientCredentialsAuth(CONFIG, transport=httpx.MockTransport(handler))

    requests = [httpx.Request("GET", "https://data-proxy.example/x") for _ in range(10)]
    await asyncio.gather(*(auth.on_request(r) for r in requests))

    assert len(handler.calls) == 1
    assert all(r.headers["Authorization"] for r in requests)

    await auth.aclose()


async def test_on_response_401_invalidates_cached_token():
    handler = token_endpoint_handler(token="stale-then-fresh")
    auth = ClientCredentialsAuth(CONFIG, transport=httpx.MockTransport(handler))

    await auth.on_request(httpx.Request("GET", "https://data-proxy.example/a"))
    assert len(handler.calls) == 1

    unauthorized = httpx.Response(401, request=httpx.Request("GET", "https://x/"))
    await auth.on_response(unauthorized)

    await auth.on_request(httpx.Request("GET", "https://data-proxy.example/b"))
    assert len(handler.calls) == 2

    await auth.aclose()


async def test_on_response_success_does_not_invalidate_cached_token():
    handler = token_endpoint_handler()
    auth = ClientCredentialsAuth(CONFIG, transport=httpx.MockTransport(handler))

    await auth.on_request(httpx.Request("GET", "https://data-proxy.example/a"))
    ok = httpx.Response(200, request=httpx.Request("GET", "https://x/"))
    await auth.on_response(ok)

    await auth.on_request(httpx.Request("GET", "https://data-proxy.example/b"))
    assert len(handler.calls) == 1

    await auth.aclose()


async def test_invalidate_forces_next_call_to_refetch():
    handler = token_endpoint_handler()
    auth = ClientCredentialsAuth(CONFIG, transport=httpx.MockTransport(handler))

    await auth.on_request(httpx.Request("GET", "https://data-proxy.example/a"))
    auth.invalidate()
    await auth.on_request(httpx.Request("GET", "https://data-proxy.example/b"))

    assert len(handler.calls) == 2

    await auth.aclose()


async def test_missing_expires_in_still_caches_with_a_default_ttl():
    handler = token_endpoint_handler(expires_in=None)
    auth = ClientCredentialsAuth(CONFIG, transport=httpx.MockTransport(handler))

    await auth.on_request(httpx.Request("GET", "https://data-proxy.example/a"))
    await auth.on_request(httpx.Request("GET", "https://data-proxy.example/b"))

    assert len(handler.calls) == 1

    await auth.aclose()


async def test_token_endpoint_error_propagates():
    async def failing_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "keycloak down"})

    auth = ClientCredentialsAuth(CONFIG, transport=httpx.MockTransport(failing_handler))

    with pytest.raises(httpx.HTTPStatusError):
        await auth.on_request(httpx.Request("GET", "https://data-proxy.example/a"))

    await auth.aclose()
