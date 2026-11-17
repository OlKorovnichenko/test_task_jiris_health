from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession


class TransactionalRepository(ABC):
    @abstractmethod
    def transaction(self) -> AbstractAsyncContextManager[None]: ...


class SQLAlchemyRepository(TransactionalRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        async with self._session.begin():
            yield
