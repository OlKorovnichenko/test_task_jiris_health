from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.events import VisitCompleted
from app.visits.models.visits import Visit


class BaseVisitRepository(ABC):
    @property
    @abstractmethod
    def session(self) -> AsyncSession: ...

    @abstractmethod
    async def get_one(self, visit_id: int) -> Visit | None: ...

    @abstractmethod
    def add_completed_event(self, event: VisitCompleted) -> None: ...
