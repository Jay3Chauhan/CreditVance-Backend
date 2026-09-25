"""
Async Redis Client with Upstash Support & Resilient In-Memory Fallback.
Provides cache-aside helpers, key pattern invalidation, and distributed locks.
"""

import certifi
import json
import time
from typing import Any, Optional
import redis.asyncio as aioredis
from loguru import logger
from app.core.config import settings


class InMemoryCacheFallback:
    """Lightweight in-memory cache fallback when Redis is unreachable or during local tests."""

    def __init__(self):
        self._store: dict[str, tuple[str, float | None]] = {}
        self._locks: set[str] = set()

    async def get(self, key: str) -> Optional[str]:
        if key in self._store:
            val, expires_at = self._store[key]
            if expires_at and time.time() > expires_at:
                del self._store[key]
                return None
            return val
        return None

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        expires_at = time.time() + ex if ex else None
        self._store[key] = (value, expires_at)
        return True

    async def delete(self, *keys: str) -> int:
        count = 0
        for k in keys:
            if k in self._store:
                del self._store[k]
                count += 1
            if k in self._locks:
                self._locks.remove(k)
        return count

    async def keys(self, pattern: str) -> list[str]:
        # Simple prefix matching
        prefix = pattern.replace("*", "")
        return [k for k in self._store.keys() if k.startswith(prefix)]

    async def setnx(self, key: str, value: str) -> bool:
        if key in self._locks:
            return False
        self._locks.add(key)
        return True

    async def ping(self) -> bool:
        return True


class RedisService:
    def __init__(self):
        self.client: Optional[aioredis.Redis] = None
        self.fallback = InMemoryCacheFallback()
        self.is_connected = False

    async def connect(self):
        if not settings.REDIS_ENABLED:
            logger.info("Redis disabled via config. Using in-memory cache fallback.")
            return

        try:
            url = settings.clean_redis_url
            kwargs: dict[str, Any] = {
                "decode_responses": True,
                "socket_timeout": 5.0,
                "socket_connect_timeout": 5.0,
                "retry_on_timeout": True,
            }
            if url.startswith("rediss://"):
                kwargs["ssl_ca_certs"] = certifi.where()

            self.client = aioredis.from_url(url, **kwargs)
            await self.client.ping()
            self.is_connected = True
            logger.info(f"Connected to Redis at {url.split('@')[-1]}")
        except Exception as e:
            logger.warning(
                f"Could not connect to Redis ({e}). Operating in resilient In-Memory fallback mode."
            )
            self.is_connected = False

    async def disconnect(self):
        if self.client and self.is_connected:
            await self.client.aclose()
            logger.info("Disconnected from Redis.")

    async def ping(self) -> bool:
        if self.is_connected and self.client:
            try:
                return bool(await self.client.ping())
            except Exception:
                return False
        return await self.fallback.ping()

    async def get_json(self, key: str) -> Optional[Any]:
        try:
            raw = (
                await self.client.get(key)
                if self.is_connected and self.client
                else await self.fallback.get(key)
            )
            if raw:
                return json.loads(raw)
            return None
        except Exception as e:
            logger.error(f"Redis get_json error for key '{key}': {e}")
            return None

    async def set_json(
        self, key: str, value: Any, ttl_seconds: Optional[int] = None
    ) -> bool:
        ttl = ttl_seconds or settings.REDIS_CACHE_TTL_SECONDS
        try:
            raw = json.dumps(value, default=str)
            if self.is_connected and self.client:
                await self.client.set(key, raw, ex=ttl)
            else:
                await self.fallback.set(key, raw, ex=ttl)
            return True
        except Exception as e:
            logger.error(f"Redis set_json error for key '{key}': {e}")
            return False

    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidates all keys matching pattern (e.g. 'catalog:*')."""
        try:
            if self.is_connected and self.client:
                keys = await self.client.keys(pattern)
                if keys:
                    return await self.client.delete(*keys)
                return 0
            else:
                keys = await self.fallback.keys(pattern)
                if keys:
                    return await self.fallback.delete(*keys)
                return 0
        except Exception as e:
            logger.error(f"Redis invalidate_pattern error for pattern '{pattern}': {e}")
            return 0

    async def acquire_lock(self, lock_key: str, ttl_seconds: int = 7200) -> bool:
        """Acquires a distributed lock using SETNX with TTL."""
        try:
            if self.is_connected and self.client:
                # Upstash Redis set with nx=True and ex=ttl_seconds
                acquired = await self.client.set(
                    lock_key, f"locked_{time.time()}", nx=True, ex=ttl_seconds
                )
                return bool(acquired)
            else:
                return await self.fallback.setnx(lock_key, f"locked_{time.time()}")
        except Exception as e:
            logger.error(f"Error acquiring lock '{lock_key}': {e}")
            return False

    async def release_lock(self, lock_key: str) -> bool:
        try:
            if self.is_connected and self.client:
                await self.client.delete(lock_key)
            else:
                await self.fallback.delete(lock_key)
            return True
        except Exception as e:
            logger.error(f"Error releasing lock '{lock_key}': {e}")
            return False


# Global Singleton Redis Service
redis_service = RedisService()
