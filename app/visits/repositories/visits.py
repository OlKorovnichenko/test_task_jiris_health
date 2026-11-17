from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.visits.models.visits import Visit
from app.visits.repositories.base import BaseVisitRepository


class VisitRepository(BaseVisitRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @property
    def session(self) -> AsyncSession:
        return self._session

    async def get_one(self, visit_id: int) -> Visit | None:
        result = select(Visit).where(Visit.id == visit_id)
        return await self._session.scalar(result)
