import hashlib
import pickle
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from src.config import env
from src.utils.log import logger

try:
    import redis
except ImportError:
    redis = None


# =============================================================================
# IN-MEMORY CACHE (L1) - Evita desserialização repetida de pickle
# =============================================================================
@dataclass
class MemoryCacheEntry:
    """Entrada do cache em memória com TTL."""
    data: Any
    expires_at: float


class InMemoryCache:
    """
    Cache em memória thread-safe com TTL.

    OTIMIZAÇÃO CRÍTICA: Evita pickle.loads() repetidos (~2-3s cada).
    Após primeira desserialização, dados ficam em memória e acesso é instant.
    """

    def __init__(self, max_size: int = 10):
        self._cache: dict[str, MemoryCacheEntry] = {}
        self._lock = threading.RLock()
        self._max_size = max_size

    def get(self, key: str) -> Any | None:
        """Busca do cache em memória. Retorna None se expirado ou não existe."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None

            # Verificar TTL
            if time.time() > entry.expires_at:
                del self._cache[key]
                logger.info(f"🧠 Memory cache EXPIRED for {key[:16]}...")
                return None

            return entry.data

    def set(self, key: str, data: Any, ttl_seconds: int) -> None:
        """Salva no cache em memória com TTL."""
        with self._lock:
            # LRU simples: se atingiu max_size, remove o mais antigo
            if len(self._cache) >= self._max_size and key not in self._cache:
                # Remove entrada mais antiga (primeiro item do dict)
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
                logger.info(f"🧠 Memory cache EVICTED {oldest_key[:16]}... (LRU)")

            self._cache[key] = MemoryCacheEntry(
                data=data,
                expires_at=time.time() + ttl_seconds
            )

    def delete(self, key: str) -> None:
        """Remove entrada do cache em memória."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                logger.info(f"🧠 Memory cache DELETED {key[:16]}...")

    def clear(self) -> None:
        """Limpa todo o cache em memória."""
        with self._lock:
            self._cache.clear()
            logger.info("🧠 Memory cache CLEARED")


# Instância global do cache em memória
_memory_cache = InMemoryCache(max_size=10)


class CacheMode(Enum):
    JSON = "json"
    REDIS = "redis"
    BOTH = "both"


class StorageBackend(ABC):
    @abstractmethod
    def load(self, key: str) -> dict[str, Any] | None:
        pass

    @abstractmethod
    def save(self, key: str, data: dict[str, Any], ttl_seconds: int) -> None:
        pass


class FileBackend(StorageBackend):
    def __init__(self, data_dir: str = ".cache/queries"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, key: str) -> Path:
        return self.data_dir / f"{key}.pickle"

    def load(self, key: str) -> dict[str, Any] | None:
        file_path = self._get_file_path(key)
        if file_path.exists():
            try:
                with open(file_path, "rb") as f:
                    data = pickle.load(f)
                    metadata = data.get("metadata", {})
                    created_at = metadata.get("created_at")
                    ttl = metadata.get("ttl")

                    if created_at and ttl and (time.time() - created_at) < ttl:
                        return data
                    else:
                        logger.info(f"File cache expired for {key[:16]}...")
                        return None
            except Exception as e:
                logger.error(f"❌ Error loading File cache for {key[:16]}...: {e}")
                return None
        return None

    def save(self, key: str, data: dict[str, Any], ttl_seconds: int) -> None:
        # Note: ttl_seconds is embedded in data["metadata"]["ttl"] and checked on load
        _ = ttl_seconds  # Explicitly mark as used (TTL is in metadata)
        file_path = self._get_file_path(key)
        try:
            file_path.parent.mkdir(
                parents=True, exist_ok=True
            )  # Ensure directory exists
            with open(file_path, "wb") as f:
                pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception as e:
            logger.error(f"❌ Error saving File cache for {key}: {e}")


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

    def load(self, key: str) -> dict[str, Any] | None:
        try:
            data = self.client.get(key)
            if data:
                return pickle.loads(data)
            return None
        except Exception as e:
            logger.error(f"❌ Redis load error for {key[:16]}...: {e}")
            return None

    def save(self, key: str, data: dict[str, Any], ttl_seconds: int) -> None:
        try:
            # OTIMIZAÇÃO: Serializar com Pickle (muito mais rápido que JSON)
            # Pickle preserva tipos do DataFrame (category, datetime, etc)
            serialized = pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)
            # Use Redis native TTL
            self.client.set(name=key, value=serialized, ex=ttl_seconds)
        except Exception as e:
            logger.error(f"❌ Redis save error for {key}: {e}")


class CacheManager:
    def __init__(
        self,
        mode: CacheMode = CacheMode.JSON,
        redis_url: str | None = None,
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

    def get(self, query: str) -> dict[str, Any] | None:
        query_hash = self._get_query_hash(query)

        # L1: Tentar cache em memória primeiro (INSTANT - evita pickle.loads)
        memory_data = _memory_cache.get(query_hash)
        if memory_data is not None:
            logger.info("🧠 Cache HIT from Memory (instant)")
            return memory_data

        # L2: Tentar Redis/File (requer pickle.loads ~2-3s)
        data = None

        # Try Redis first if enabled
        if self.mode in (CacheMode.REDIS, CacheMode.BOTH) and self.redis_backend:
            data = self.redis_backend.load(query_hash)
            if data:
                logger.info("💾 Cache HIT from Redis ♨️ (deserializing...)")

        # Fallback to File (Pickle) if enabled and missed in Redis (or Redis disabled)
        if not data and self.mode in (CacheMode.JSON, CacheMode.BOTH):
            data = self.file_backend.load(query_hash)
            if data:
                logger.info("💾 Cache HIT from File 📝 (deserializing...)")

        if not data:
            return None

        # Extrair dados e TTL restante
        metadata = data.get("metadata", {})
        expires_at = metadata.get("expires_at", 0)
        remaining_ttl = max(1, int(expires_at - time.time()))

        # Promover para L1 (cache em memória) para próximas requests
        result_data = data["data"]
        _memory_cache.set(query_hash, result_data, remaining_ttl)
        logger.info(f"🧠 Promoted to Memory cache (TTL: {remaining_ttl}s)")

        return result_data

    def set(
        self,
        query: str,
        data: Any,
        ttl: int | None = None,
        profiling_data: dict[str, Any] | None = None,
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

        # L1: Salvar no cache em memória (acesso instant para próximas requests)
        _memory_cache.set(query_hash, data, ttl)

        # L2: Save to File (Pickle) if enabled
        if self.mode in (CacheMode.JSON, CacheMode.BOTH):
            self.file_backend.save(query_hash, cache_object, ttl)

        # L2: Save to Redis if enabled (uses native TTL)
        if self.mode in (CacheMode.REDIS, CacheMode.BOTH) and self.redis_backend:
            self.redis_backend.save(query_hash, cache_object, ttl)

    def delete(self, query: str) -> None:
        """
        Invalidate cache for a specific query.

        SEGURANÇA: Usado após INSERT/UPDATE/DELETE para evitar race conditions.
        Ao invés de fazer bypass_cache=True (que força nova query imediata),
        apenas invalida o cache. Próxima request vai popular o cache naturalmente.

        Args:
            query: SQL query to invalidate cache for
        """
        query_hash = self._get_query_hash(query)

        # L1: Delete from Memory cache first (instant)
        _memory_cache.delete(query_hash)

        # L2: Delete from File backend if enabled
        if self.mode in (CacheMode.JSON, CacheMode.BOTH):
            import os

            cache_file = os.path.join(self.file_backend.data_dir, f"{query_hash}.pkl")
            if os.path.exists(cache_file):
                os.remove(cache_file)
                logger.info(f"🗑️  Cache invalidated (File): {query_hash[:8]}...")

        # L2: Delete from Redis if enabled
        if self.mode in (CacheMode.REDIS, CacheMode.BOTH) and self.redis_backend:
            self.redis_backend.client.delete(query_hash)
            logger.info(f"🗑️  Cache invalidated (Redis): {query_hash[:8]}...")


if env.USE_LOCAL_API:
    _MODE = CacheMode.JSON
else:
    _MODE = CacheMode.REDIS

# Global Instance
query_cache = CacheManager(mode=_MODE, redis_url=env.REDIS_URL)
