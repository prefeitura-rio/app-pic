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

import httpx
from postgrest import (
    AsyncPostgrestClient,
    AsyncRequestBuilder,
    AsyncRPCFilterRequestBuilder,
)

from src.pic.infrastructure.postgrest_client.auth import ClientCredentialsAuth
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
        self._auth = ClientCredentialsAuth(config, transport=transport)
        self._http_client = httpx.AsyncClient(
            base_url=config.base_url,
            event_hooks={
                "request": [self._auth.on_request],
                "response": [self._auth.on_response],
            },
            timeout=10.0,
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

    def rpc(self, func: str, params: dict) -> AsyncRPCFilterRequestBuilder:
        """Call one PostgREST stored procedure (`POST /rpc/<func>`)."""
        return self._postgrest.rpc(func, params)

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
