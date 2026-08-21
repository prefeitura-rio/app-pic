"""Keycloak client_credentials auth for the data-proxy PostgREST client.

`postgrest.AsyncPostgrestClient` always passes `auth=None` explicitly on every
request it issues (see `postgrest/_async/client.py`), and httpx treats an
explicit `auth=None` as "use no authentication for this request" - it
silently overrides any `httpx.Auth` attached to the client. Because of that,
token injection here is implemented as an httpx *event hook* instead of an
`httpx.Auth` flow: event hooks run unconditionally for every request/response,
regardless of the per-request `auth=` argument.

One consequence of using event hooks: a request can't be transparently
retried after a 401 (event hooks can't replay a request). Instead, tokens are
refreshed proactively before they expire, and a 401 response only invalidates
the cached token so the *next* call fetches a fresh one.
"""

import asyncio
import time

import httpx

from src.pic.infrastructure.postgrest_client.config import PostgrestClientConfig

# Refresh this many seconds before the token's reported expiry, to absorb
# request latency and clock drift between this process and Keycloak.
_EXPIRY_LEEWAY_SECONDS = 10.0

# Used only when a token response omits `expires_in` (should not happen with
# Keycloak, but avoids caching a token forever if it ever does).
_DEFAULT_TTL_SECONDS = 60.0


class ClientCredentialsAuth:
    """Fetches, caches, and refreshes a Keycloak client_credentials bearer token.

    Attach `on_request`/`on_response` as httpx `event_hooks` on the
    `httpx.AsyncClient` used to talk to the data-proxy, so every request
    transparently carries a valid bearer token without `postgrest` needing to
    know tokens exist.

    A single in-flight refresh is shared between concurrent requests via an
    `asyncio.Lock`, so a cold cache under concurrent load triggers one token
    request, not one per waiting request.
    """

    def __init__(
        self,
        config: PostgrestClientConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """`transport` is a test seam (e.g. `httpx.MockTransport`); leave it
        `None` in production to use real network I/O."""
        self._token_url = config.token_url
        self._client_id = config.client_id
        self._client_secret = config.client_secret

        # Separate client dedicated to the token endpoint - it carries no
        # event hooks of its own, so it can't recurse into these hooks.
        self._token_http_client = httpx.AsyncClient(timeout=10.0, transport=transport)

        self._token: str | None = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()

    async def on_request(self, request: httpx.Request) -> None:
        """httpx request event hook: attach a valid bearer token."""
        request.headers["Authorization"] = f"Bearer {await self._get_token()}"

    async def on_response(self, response: httpx.Response) -> None:
        """httpx response event hook: drop a token the server rejected.

        Doesn't retry the failed request (event hooks can't replay it); the
        next call will fetch a fresh token via `on_request`.
        """
        if response.status_code == httpx.codes.UNAUTHORIZED:
            self.invalidate()

    def invalidate(self) -> None:
        """Force the next call to fetch a fresh token."""
        self._token = None
        self._expires_at = 0.0

    async def aclose(self) -> None:
        await self._token_http_client.aclose()

    async def _get_token(self) -> str:
        if self._token is not None and time.monotonic() < self._expires_at:
            return self._token

        async with self._lock:
            # Another caller may have refreshed while this one waited for the lock.
            if self._token is None or time.monotonic() >= self._expires_at:
                await self._refresh()

        assert self._token is not None
        return self._token

    async def _refresh(self) -> None:
        response = await self._token_http_client.post(
            self._token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
        )
        response.raise_for_status()
        payload = response.json()

        expires_in = payload.get("expires_in", _DEFAULT_TTL_SECONDS)
        self._token = payload["access_token"]
        self._expires_at = time.monotonic() + expires_in - _EXPIRY_LEEWAY_SECONDS
