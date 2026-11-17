from abc import ABC, abstractmethod
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


class BaseBillingRepository(ABC):
    @property
    @abstractmethod
    def session(self) -> AsyncSession: ...

    @abstractmethod
    async def claim_event(self, event_id: UUID) -> bool: ...

    @abstractmethod
    async def create_bill(self, visit_id: int, amount: Decimal) -> None: ...
