"""Cache abstraction.

Uses Redis when ``REDIS_URL`` is configured, otherwise a thread-safe in-process
TTL cache. Callers use the same interface either way.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


class _MemoryCache:
    def __init__(self) -> None:
        self._store: dict[str, tuple[float | None, Any]] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at is not None and expires_at < time.time():
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        with self._lock:
            self._store[key] = (time.time() + ttl if ttl else None, value)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def incr(self, key: str, amount: int = 1, ttl: int | None = None) -> int:
        with self._lock:
            current = self.get(key) or 0
            new = int(current) + amount
            expires_at = time.time() + ttl if ttl else None
            existing = self._store.get(key)
            if existing and existing[0] is not None:
                expires_at = existing[0]
            self._store[key] = (expires_at, new)
            return new

    def keys(self, prefix: str = "") -> list[str]:
        with self._lock:
            return [k for k in self._store if k.startswith(prefix)]

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


class _RedisCache:
    def __init__(self, url: str) -> None:
        import redis  # imported lazily; optional dependency

        self._client = redis.Redis.from_url(url, decode_responses=True)

    def get(self, key: str) -> Any | None:
        raw = self._client.get(key)
        if raw is None:
            return None
        try:
            import json

            return json.loads(raw)
        except Exception:
            return raw

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        import json

        self._client.set(key, json.dumps(value, default=str), ex=ttl)

    def delete(self, key: str) -> None:
        self._client.delete(key)

    def incr(self, key: str, amount: int = 1, ttl: int | None = None) -> int:
        pipe = self._client.pipeline()
        pipe.incrby(key, amount)
        if ttl:
            pipe.expire(key, ttl)
        return int(pipe.execute()[0])

    def keys(self, prefix: str = "") -> list[str]:
        return [k for k in self._client.scan_iter(match=f"{prefix}*")]

    def clear(self) -> None:
        for key in self.keys():
            self._client.delete(key)


_cache: Any = None


def get_cache() -> Any:
    global _cache
    if _cache is None:
        if settings.redis_url:
            try:
                _cache = _RedisCache(settings.redis_url)
                log.info("cache backend: redis")
            except Exception as exc:  # pragma: no cover - depends on env
                log.warning("redis unavailable (%s); using in-process cache", exc)
                _cache = _MemoryCache()
        else:
            _cache = _MemoryCache()
            log.info("cache backend: in-process")
    return _cache
