from abc import ABC, abstractmethod
from decimal import Decimal
from uuid import UUID

from app.common.database.transactions import TransactionalRepository


class BaseBillingRepository(TransactionalRepository, ABC):
    @abstractmethod
    async def claim_event(self, event_id: UUID) -> bool: ...

    @abstractmethod
    async def create_bill(self, visit_id: int, amount: Decimal) -> None: ...
