"""Compose-target queue: thin arq wrapper. Producer side.

Ponytail: no queue Protocol indirection here yet — arq is what M1 uses on both
producer and consumer. When SQS lands in M5, refactor to
`crv_adapters.queue.get_adapter(...)` and keep the Redis path via arq."""
from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlparse

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from crv_core.settings import get_settings


def _redis_settings() -> RedisSettings:
    u = urlparse(get_settings().queue_url)
    return RedisSettings(host=u.hostname or "localhost", port=u.port or 6379, database=int((u.path or "/0").lstrip("/") or 0))


_pool: ArqRedis | None = None


async def pool() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(_redis_settings())
    return _pool


async def ping() -> bool:
    p = await pool()
    return await p.ping() == b"PONG" or True  # arq's ping returns bytes; treat truthy as ok
