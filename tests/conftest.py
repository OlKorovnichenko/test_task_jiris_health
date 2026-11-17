from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.common.database.session import get_session
from app.common.setting.config import settings
from app.main import app


@pytest_asyncio.fixture
async def db_connection() -> AsyncIterator[AsyncConnection]:
    engine = create_async_engine(settings.postgres_url)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                yield connection
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_connection: AsyncConnection) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(
        bind=db_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    async with factory() as session:
        yield session


@pytest.fixture
def request_sessions() -> list[AsyncSession]:
    return []


@pytest_asyncio.fixture
async def client(
    db_connection: AsyncConnection, request_sessions: list[AsyncSession]
) -> AsyncIterator[AsyncClient]:
    factory = async_sessionmaker(
        bind=db_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            request_sessions.append(session)
            yield session

    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_session] = override_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
