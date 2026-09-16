"""Async PostgREST client for the data-proxy service.

Generic, schema-scoped wrapper around `postgrest.AsyncPostgrestClient`:
authentication (Keycloak client_credentials, see `auth.py`) is wired once at
construction time via httpx event hooks and handled transparently for every
request after that - callers just build and `.execute()` a query, same as
with the bare library.

This module owns no domain knowledge (no `rls.access_policy` column names, no
participant schema). Domain-specific repositories build on top of `.table()`/
`.rpc()`, one per data-proxy consumer (admin policy writes today; participant
reads once that migration happens).
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from postgrest import (
    AsyncPostgrestClient,
    AsyncRequestBuilder,
    AsyncRPCFilterRequestBuilder,
)

from src.pic.infrastructure.postgrest_client.auth import (
    ClientCredentialsAuth,
    user_token_override,
)
from src.pic.infrastructure.postgrest_client.config import (
    PostgrestClientConfig,
    load_config,
)


class PostgrestClient:
    """One authenticated connection to one data-proxy schema.

    Owns a pooled `httpx.AsyncClient` - construct once per process (see
    `get_postgrest_client()`) and reuse it; do not create one per request.
    """

    def __init__(
        self,
        config: PostgrestClientConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """`transport` is a test seam (e.g. `httpx.MockTransport`); leave it
        `None` in production to use real network I/O."""
        self._config = config
        self._auth = ClientCredentialsAuth(config, transport=transport)
        self._http_client = httpx.AsyncClient(
            base_url=config.base_url,
            event_hooks={
                "request": [self._auth.on_request],
                "response": [self._auth.on_response],
            },
            timeout=20.0,
            transport=transport,
        )
        self._postgrest = AsyncPostgrestClient(
            config.base_url,
            schema=config.schema,
            http_client=self._http_client,
        )

    def table(self, name: str) -> AsyncRequestBuilder:
        """Return a query builder for one table/view in the configured schema."""
        return self._postgrest.from_(name)

    @asynccontextmanager
    async def with_user_token(
        self, token: str | None
    ) -> AsyncIterator["PostgrestClient"]:
        """Scope every request made inside the block to the given user JWT.

        Sets `user_token_override` so `ClientCredentialsAuth.on_request`
        sends `Bearer <token>` instead of the Keycloak client_credentials
        token, letting PostgREST enforce row-level security for that user.
        The override is reset when the block exits; a `None` token means
        "fall back to client_credentials" (e.g. data-proxy roles that bypass
        RLS). The ContextVar is per-asyncio-task, so concurrent requests are
        unaffected.
        """
        reset_token = user_token_override.set(token)
        try:
            yield self
        finally:
            user_token_override.reset(reset_token)

    def rpc(self, func: str, params: dict) -> AsyncRPCFilterRequestBuilder:
        """Call one PostgREST stored procedure (`POST /rpc/<func>`)."""
        return self._postgrest.rpc(func, params)

    def for_schema(self, schema: str) -> AsyncPostgrestClient:
        """Return a raw `AsyncPostgrestClient` scoped to a different PostgREST
        schema (`Accept-Profile`/`Content-Profile`), reusing this instance's
        authenticated `httpx.AsyncClient` (same connection pool, same bearer
        token event hooks).

        Safe to share the underlying http client across schemas: each
        `AsyncPostgrestClient` keeps its own copy of those headers and
        injects them per-request from its own request builders, rather than
        mutating the shared client's default headers. Confirmed by reading
        `postgrest/_async/client.py` (`AsyncPostgrestClient.__init__` builds
        `self.headers` once and passes it down to every `AsyncRequestBuilder`
        it creates) and validated empirically with two schemas sharing one
        `httpx.AsyncClient`.
        """
        return AsyncPostgrestClient(
            self._config.base_url, schema=schema, http_client=self._http_client
        )

    async def aclose(self) -> None:
        await self._http_client.aclose()
        await self._auth.aclose()


_client: PostgrestClient | None = None
_init_lock = asyncio.Lock()


async def get_postgrest_client() -> PostgrestClient:
    """Lazily create the (singleton) data-proxy client for the app's schema."""
    global _client
    if _client is None:
        async with _init_lock:
            if _client is None:
                _client = PostgrestClient(load_config())
    return _client


async def close_postgrest_client() -> None:
    """Close the singleton client. Call on app shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
