from abc import ABC, abstractmethod

from app.common.database.transactions import TransactionalRepository
from app.common.events import VisitCompleted
from app.visits.models.visits import Visit


class BaseVisitRepository(TransactionalRepository, ABC):
    @abstractmethod
    async def get_for_update(self, visit_id: int) -> Visit | None: ...

    @abstractmethod
    def add_completed_event(self, event: VisitCompleted) -> None: ...
