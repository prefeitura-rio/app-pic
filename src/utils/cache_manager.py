import os
import hashlib
import time
import pickle
from pathlib import Path
from enum import Enum
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import datetime

from src.config import env
from src.utils.log import logger

try:
    import redis
except ImportError:
    redis = None


class CacheMode(Enum):
    JSON = "json"
    REDIS = "redis"
    BOTH = "both"


class StorageBackend(ABC):
    @abstractmethod
    def load(self, key: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def save(self, key: str, data: Dict[str, Any], ttl_seconds: int) -> None:
        pass


class FileBackend(StorageBackend):
    def __init__(self, data_dir: str = ".cache/queries"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, key: str) -> Path:
        return self.data_dir / f"{key}.pickle"

    def load(self, key: str) -> Optional[Dict[str, Any]]:
        file_path = self._get_file_path(key)
        if file_path.exists():
            try:
                with open(file_path, "rb") as f:
                    # Pickle backend still needs to handle its own TTL check
                    data = pickle.load(f)
                    metadata = data.get("metadata", {})
                    created_at = metadata.get("created_at")
                    ttl = metadata.get("ttl")

                    if created_at and ttl and (time.time() - created_at) < ttl:
                        return data
                    else:
                        logger.info(f"File cache expired for {key}")
                        # Optionally delete expired file
                        # os.remove(file_path)
                        return None
            except Exception as e:
                logger.error(f"Error loading File cache for {key}: {e}")
                return None
        return None

    def save(self, key: str, data: Dict[str, Any], ttl_seconds: int) -> None:
        file_path = self._get_file_path(key)
        try:
            file_path.parent.mkdir(
                parents=True, exist_ok=True
            )  # Ensure directory exists
            with open(file_path, "wb") as f:
                pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception as e:
            logger.error(f"Error saving File cache for {key}: {e}")


class RedisBackend(StorageBackend):
    def __init__(self, redis_url: str):
        if redis is None:
            raise ImportError("redis-py library is required for RedisBackend")
        # OTIMIZAÇÃO CRÍTICA: decode_responses=False para permitir salvar bytes (Pickle)
        # Pickle é ~10x mais rápido que JSON para DataFrames
        self.client = redis.Redis.from_url(
            redis_url,
            decode_responses=False,
            socket_connect_timeout=5,
            socket_timeout=5,
        )

    def load(self, key: str) -> Optional[Dict[str, Any]]:
        try:
            data = self.client.get(key)
            if data:
                # OTIMIZAÇÃO: Desserializar Pickle (suporta DataFrames nativamente)
                return pickle.loads(data)
            return None
        except Exception as e:
            logger.error(f"Redis load error for {key}: {e}")
            return None

    def save(self, key: str, data: Dict[str, Any], ttl_seconds: int) -> None:
        try:
            # OTIMIZAÇÃO: Serializar com Pickle (muito mais rápido que JSON)
            # Pickle preserva tipos do DataFrame (category, datetime, etc)
            serialized = pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)
            # Use Redis native TTL
            self.client.set(name=key, value=serialized, ex=ttl_seconds)
        except Exception as e:
            logger.error(f"Redis save error for {key}: {e}")


class CacheManager:
    def __init__(
        self,
        mode: CacheMode = CacheMode.JSON,
        redis_url: Optional[str] = None,
        default_ttl: int = env.CACHE_TTL_SECONDS,  # 5 minutes default
        data_dir: str = ".cache/queries",
    ):
        self.mode = mode
        self.default_ttl = default_ttl

        self.file_backend = FileBackend(data_dir)
        self.redis_backend = None

        if mode in (CacheMode.REDIS, CacheMode.BOTH):
            if not redis_url:
                raise ValueError("Redis URL required for REDIS/BOTH modes")
            self.redis_backend = RedisBackend(redis_url)

    def _get_query_hash(self, query: str) -> str:
        return hashlib.sha256(query.encode("utf-8")).hexdigest()

    def get(self, query: str) -> Optional[Dict[str, Any]]:
        query_hash = self._get_query_hash(query)
        data = None

        # Try Redis first if enabled
        if self.mode in (CacheMode.REDIS, CacheMode.BOTH) and self.redis_backend:
            data = self.redis_backend.load(query_hash)
            if data:
                logger.info("💾 Cache HIT from Redis ♨️")

        # Fallback to File (Pickle) if enabled and missed in Redis (or Redis disabled)
        if not data and self.mode in (CacheMode.JSON, CacheMode.BOTH):
            data = self.file_backend.load(
                query_hash
            )  # File backend handles its own TTL check
            if data:
                logger.info("💾 Cache HIT from File 📝")

        if not data:
            return None

        # Update Metadata (only for File, Redis expiration is native)
        metadata = data.get("metadata", {})

        now = time.time()
        metadata["checked_at"] = now
        metadata["checked_count"] = metadata.get("checked_count", 0) + 1

        return data["data"]

    def set(
        self,
        query: str,
        data: Any,
        ttl: Optional[int] = None,
        profiling_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        query_hash = self._get_query_hash(query)
        ttl = ttl or self.default_ttl
        now = time.time()

        metadata = {
            "created_at": now,
            "expires_at": now
            + ttl,  # This is for JSON/Pickle consistency, Redis handles native expiry
            "checked_at": now,
            "ttl": ttl,
            "expires_in": ttl,
            "checked_count": 0,
            "query": query,
        }
        if profiling_data:
            metadata["profiling"] = profiling_data

        cache_object = {
            "metadata": metadata,
            "data": data,
        }

        # Save to File (Pickle) if enabled
        if self.mode in (CacheMode.JSON, CacheMode.BOTH):
            self.file_backend.save(query_hash, cache_object, ttl)

        # Save to Redis if enabled (uses native TTL)
        if self.mode in (CacheMode.REDIS, CacheMode.BOTH) and self.redis_backend:
            self.redis_backend.save(query_hash, cache_object, ttl)


if env.USE_LOCAL_API:
    _MODE = CacheMode.JSON
else:
    _MODE = CacheMode.REDIS

# Global Instance
query_cache = CacheManager(mode=_MODE, redis_url=env.REDIS_URL)
