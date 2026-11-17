from decimal import Decimal
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.models.billing import (
    BillingRecord,
    ProcessedBillingEvent,
)
from app.billing.repositories.base import BaseBillingRepository
from app.billing.utils.enumerations.billing_enums import BillingStatus


class BillingRepository(BaseBillingRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @property
    def session(self) -> AsyncSession:
        return self._session

    async def claim_event(self, event_id: UUID) -> bool:
        bill_event = (
            insert(ProcessedBillingEvent)
            .values(event_id=event_id)
            .on_conflict_do_nothing(index_elements=[ProcessedBillingEvent.event_id])
            .returning(ProcessedBillingEvent.event_id)
        )
        return await self._session.scalar(bill_event) is not None

    async def create_bill(self, visit_id: int, amount: Decimal) -> None:
        bill = (
            insert(BillingRecord)
            .values(visit_id=visit_id, amount=amount, status=BillingStatus.CREATED)
            .on_conflict_do_nothing(index_elements=[BillingRecord.visit_id])
        )
        await self._session.execute(bill)
