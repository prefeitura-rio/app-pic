"""Async Redis client singleton for the V2 dashboard cache.

Mirrors the lazy-singleton pattern of ``postgrest_client/client.py``:

* One ``redis.asyncio.Redis`` instance is created on first use and reused for
  the lifetime of the process.
* ``get_redis_client()`` is safe to call from any async context (including
  FastAPI dependency functions).
* ``close_redis_client()`` should be called on app shutdown (wired via
  FastAPI lifespan or ``atexit`` — the caller's responsibility).

The Redis URL is read from ``src.config.env.REDIS_URL``.  If the URL is
absent or the connection fails, the helper logs a warning and returns ``None``
so the repository degrades gracefully (cache disabled, no error raised).
"""

from __future__ import annotations

import asyncio
from typing import Any

from src.config import env
from src.utils.log import logger

try:
    import redis.asyncio as aioredis
except ImportError:  # pragma: no cover
    aioredis = None  # type: ignore[assignment]

_redis_client: Any | None = None
_redis_lock = asyncio.Lock()


async def get_redis_client() -> Any | None:
    """Return the shared async Redis client, creating it on first call.

    Returns ``None`` if redis-py is not installed or the URL is unavailable,
    so callers can treat it as an optional dependency.
    """
    global _redis_client

    if aioredis is None:
        logger.warning("[redis] redis-py not installed; dashboard cache disabled")
        return None

    redis_url: str | None = getattr(env, "REDIS_URL", None)
    if not redis_url:
        logger.warning("[redis] REDIS_URL not set; dashboard cache disabled")
        return None

    if _redis_client is not None:
        return _redis_client

    async with _redis_lock:
        if _redis_client is None:
            try:
                _redis_client = aioredis.from_url(
                    redis_url,
                    encoding="utf-8",
                    decode_responses=False,  # we handle bytes ourselves
                    socket_connect_timeout=2,
                    socket_timeout=2,
                )
                # Smoke-test the connection
                await _redis_client.ping()
                logger.info("[redis] async Redis client initialised")
            except Exception as exc:
                logger.warning(f"[redis] could not connect to Redis ({exc}); cache disabled")
                _redis_client = None

    return _redis_client


async def close_redis_client() -> None:
    """Close the singleton Redis client. Call on app shutdown."""
    global _redis_client
    if _redis_client is not None:
        try:
            await _redis_client.aclose()
        except Exception:
            pass
        _redis_client = None
        logger.info("[redis] async Redis client closed")
