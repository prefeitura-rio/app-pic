import httpx
import pytest
from postgrest.exceptions import APIError

from src.pic.infrastructure.postgrest_client import client as client_module
from src.pic.infrastructure.postgrest_client.client import (
    PostgrestClient,
    close_postgrest_client,
    get_postgrest_client,
)
from src.pic.infrastructure.postgrest_client.config import PostgrestClientConfig

CONFIG = PostgrestClientConfig(
    base_url="https://data-proxy.example/",
    schema="app_pequenos_cariocas",
    token_url="https://keycloak.example/token",
    client_id="pic-client",
    client_secret="pic-secret",
)


def fake_data_proxy(*, valid_token: str = "good-token"):
    """Fakes both the Keycloak token endpoint and the data-proxy API behind
    one MockTransport, keyed by host. Records every non-token request."""
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "keycloak.example":
            return httpx.Response(
                200, json={"access_token": valid_token, "expires_in": 3600}
            )

        requests.append(request)
        if request.headers.get("authorization") != f"Bearer {valid_token}":
            return httpx.Response(
                401,
                json={
                    "message": "unauthorized",
                    "code": "401",
                    "hint": None,
                    "details": None,
                },
            )

        if request.url.path == "/rpc/promote_user":
            return httpx.Response(200, json={"promoted": True})

        if request.method == "POST":
            return httpx.Response(201, json=[{"id": 1, **(request_json(request))}])

        return httpx.Response(200, json=[{"id": 1, "cpf": "12345678900"}])

    handler.requests = requests  # type: ignore[attr-defined]
    return handler


def request_json(request: httpx.Request) -> dict:
    import json

    return json.loads(request.content or b"{}")


def make_client(handler) -> PostgrestClient:
    return PostgrestClient(CONFIG, transport=httpx.MockTransport(handler))


async def test_table_select_is_authenticated_and_scoped_to_schema():
    handler = fake_data_proxy()
    client = make_client(handler)

    result = await client.table("access_policy").select("*").execute()

    assert result.data == [{"id": 1, "cpf": "12345678900"}]
    sent = handler.requests[0]
    assert sent.headers["accept-profile"] == "app_pequenos_cariocas"
    assert sent.headers["authorization"] == "Bearer good-token"

    await client.aclose()


async def test_table_insert_sends_json_body_to_configured_schema():
    handler = fake_data_proxy()
    client = make_client(handler)

    result = await (
        client.table("access_policy")
        .insert({"cpf": "12345678900", "unit_type": "cras"})
        .execute()
    )

    assert result.data[0]["cpf"] == "12345678900"
    sent = handler.requests[0]
    assert sent.headers["content-profile"] == "app_pequenos_cariocas"

    await client.aclose()


async def test_rpc_calls_the_named_procedure_with_params():
    handler = fake_data_proxy()
    client = make_client(handler)

    result = await client.rpc("promote_user", {"cpf": "12345678900"}).execute()

    assert result.data == {"promoted": True}
    sent = handler.requests[0]
    assert sent.url.path == "/rpc/promote_user"

    await client.aclose()


async def test_request_without_valid_token_raises_api_error():
    handler = fake_data_proxy(valid_token="right-token")
    client = make_client(handler)
    # Force a bad cached token so the fake server rejects the request.
    client._auth._token = "wrong-token"
    client._auth._expires_at = float("inf")

    with pytest.raises(APIError):
        await client.table("access_policy").select("*").execute()

    await client.aclose()


async def test_for_schema_shares_auth_and_scopes_to_the_new_schema():
    handler = fake_data_proxy()
    client = make_client(handler)

    rls_client = client.for_schema("rls")
    await rls_client.from_("access_policy").select("*").execute()

    sent = handler.requests[0]
    assert sent.headers["accept-profile"] == "rls"
    assert sent.headers["authorization"] == "Bearer good-token"

    await client.aclose()


async def test_for_schema_does_not_leak_into_the_original_schema():
    handler = fake_data_proxy()
    client = make_client(handler)

    client.for_schema("rls")
    await client.table("access_policy").select("*").execute()

    sent = handler.requests[0]
    assert sent.headers["accept-profile"] == "app_pequenos_cariocas"

    await client.aclose()


async def test_get_postgrest_client_returns_singleton(monkeypatch):
    monkeypatch.setattr(client_module, "load_config", lambda: CONFIG)
    client_module._client = None

    first = await get_postgrest_client()
    second = await get_postgrest_client()

    assert first is second

    await close_postgrest_client()


async def test_close_postgrest_client_resets_singleton(monkeypatch):
    monkeypatch.setattr(client_module, "load_config", lambda: CONFIG)
    client_module._client = None

    first = await get_postgrest_client()
    await close_postgrest_client()
    assert client_module._client is None

    second = await get_postgrest_client()
    assert second is not first

    await close_postgrest_client()
