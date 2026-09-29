"""Redis-backed cache facade for the participant PostgREST repository.

Wraps the raw Redis client with the serialization and error handling the
repository used to do inline: participant list pages and filter-option lists
are stored as JSON payloads; reads/writes are best-effort (errors are logged
and swallowed, never propagated to the caller). Kept out of `helpers/` (pure
Python only) because it performs I/O.
"""

import json
from typing import Any

from src.pic.domain.models.filters import FilterOption
from src.pic.domain.models.pagination import PaginationMeta
from src.pic.domain.models.participante import ParticipanteListItem
from src.pic.infrastructure.repositories.helpers.participant_columns import (
    CACHE_TTL_SECONDS,
)
from src.utils.log import logger


class ParticipantCache:
    """Best-effort Redis cache for participant list and filter options."""

    def __init__(self, redis_client: Any = None) -> None:
        self._redis = redis_client

    @property
    def enabled(self) -> bool:
        """True when a Redis client is wired (caching is optional)."""
        return self._redis is not None

    async def get_list(
        self, key: str
    ) -> tuple[list[ParticipanteListItem], PaginationMeta] | None:
        try:
            raw = await self._redis.get(key)
            if raw is None:
                return None
            payload = json.loads(raw)
            data = [
                ParticipanteListItem.model_validate(item) for item in payload["data"]
            ]
            meta = PaginationMeta.model_validate(payload["meta"])
            meta.cache_hit = True
            logger.info(f"[participants] cache HIT ({len(data)} rows)")
            return data, meta
        except Exception as exc:
            logger.warning(f"[participants] cache read error (ignoring): {exc}")
            return None

    async def set_list(
        self,
        key: str,
        data: list[ParticipanteListItem],
        meta: PaginationMeta,
        ttl: int | None = None,
    ) -> None:
        try:
            payload = json.dumps(
                {
                    "data": [item.model_dump(mode="json") for item in data],
                    "meta": meta.model_dump(mode="json"),
                }
            )
            ttl = CACHE_TTL_SECONDS if ttl is None else ttl
            await self._redis.set(key, payload, ex=ttl)
            logger.info(f"[participants] cache SET ({len(data)} rows, TTL {ttl}s)")
        except Exception as exc:
            logger.warning(f"[participants] cache write error (ignoring): {exc}")

    async def get_vocab(self, key: str) -> list[FilterOption] | None:
        try:
            raw = await self._redis.get(key)
            if raw is None:
                return None
            logger.info("[filters] cache HIT")
            return [FilterOption.model_validate(item) for item in json.loads(raw)]
        except Exception as exc:
            logger.warning(f"[filters] cache read error (ignoring): {exc}")
            return None

    async def set_vocab(self, key: str, options: list[FilterOption]) -> None:
        try:
            payload = json.dumps([opt.model_dump(mode="json") for opt in options])
            await self._redis.set(key, payload, ex=CACHE_TTL_SECONDS)
            logger.info(f"[filters] cache SET (TTL {CACHE_TTL_SECONDS}s)")
        except Exception as exc:
            logger.warning(f"[filters] cache write error (ignoring): {exc}")
