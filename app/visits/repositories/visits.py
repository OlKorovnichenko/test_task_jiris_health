from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.events import VisitCompleted
from app.visits.models.outbox import VisitOutboxEvent
from app.visits.models.visits import Visit
from app.visits.repositories.base import BaseVisitRepository


class VisitRepository(BaseVisitRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @property
    def session(self) -> AsyncSession:
        return self._session

    async def get_one(self, visit_id: int) -> Visit | None:
        result = select(Visit).where(Visit.id == visit_id).with_for_update()
        return await self._session.scalar(result)

    def add_completed_event(self, event: VisitCompleted) -> None:
        self._session.add(
            VisitOutboxEvent(
                event_id=event.event_id,
                visit_id=event.visit_id,
                payload=event.model_dump(mode="json"),
            )
        )
