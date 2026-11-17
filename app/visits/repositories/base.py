from abc import ABC, abstractmethod

from app.common.database.transactions import TransactionalRepository
from app.common.events import VisitCompleted
from app.visits.models.visits import Visit
from app.visits.utils.outbox import OutboxClaim


class BaseVisitRepository(TransactionalRepository, ABC):
    @abstractmethod
    async def get_for_update(self, visit_id: int) -> Visit | None: ...

    @abstractmethod
    def add_completed_event(self, event: VisitCompleted) -> None: ...


class BaseOutboxRepository(ABC):
    @abstractmethod
    async def claim_next_pending(self) -> OutboxClaim | None: ...

    @abstractmethod
    async def mark_published(self, claim: OutboxClaim) -> None: ...

    @abstractmethod
    async def release_claim(self, claim: OutboxClaim) -> None: ...
