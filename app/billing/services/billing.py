from datetime import UTC, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.billing.repositories.base import BaseBillingRepository
from app.billing.services.base import BaseBillingService
from app.common.events import VisitCompleted


class BillingService(BaseBillingService):
    def __init__(self, repository: BaseBillingRepository) -> None:
        self._repository = repository

    @staticmethod
    def _calculate_amount(event: VisitCompleted) -> Decimal:
        duration = event.end_date_time.astimezone(
            UTC
        ) - event.start_date_time.astimezone(UTC)
        hours = Decimal(duration // timedelta(microseconds=1)) / Decimal(3_600_000_000)
        return (hours * event.rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    async def process_visit_completed(self, event: VisitCompleted) -> None:
        async with self._repository.transaction():
            if not await self._repository.claim_event(event.event_id):
                return
            amount = self._calculate_amount(event)
            if amount < 0:
                raise ValueError("Billing amount must be non-negative")
            await self._repository.create_bill(event.visit_id, amount)
