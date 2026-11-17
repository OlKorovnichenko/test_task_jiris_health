from collections.abc import AsyncIterator
from dataclasses import dataclass
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.common.setting.config import get_settings


@dataclass(frozen=True)
class Database:
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]


@lru_cache
def get_database() -> Database:
    engine = create_async_engine(get_settings().postgres_url, pool_pre_ping=True)
    return Database(engine, async_sessionmaker(engine, expire_on_commit=False))


async def dispose_database() -> None:
    if get_database.cache_info().currsize:
        await get_database().engine.dispose()
        get_database.cache_clear()


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_database().sessions() as session:
        yield session
