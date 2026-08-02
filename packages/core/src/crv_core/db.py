"""Async SQLAlchemy engine + session factory. Shared by api and worker."""
from __future__ import annotations

from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from crv_core.settings import get_settings


@lru_cache
def engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine(), expire_on_commit=False)


async def ping() -> bool:
    from sqlalchemy import text
    async with engine().connect() as c:
        return (await c.scalar(text("SELECT 1"))) == 1
