from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.sql.dml import Update

from app.common.database.transactions import SQLAlchemyRepository
from app.visits.models.outbox import VisitOutboxEvent
from app.visits.repositories.base import BaseOutboxRepository
from app.visits.utils.outbox import OutboxClaim


class OutboxRepository(SQLAlchemyRepository, BaseOutboxRepository):
    async def claim_next_pending(self) -> OutboxClaim | None:
        async with self.transaction():
            now = datetime.now(UTC)
            token = uuid4()
            pending_event = (
                select(VisitOutboxEvent.event_id)
                .where(
                    VisitOutboxEvent.published_at.is_(None),
                    or_(
                        VisitOutboxEvent.claimed_until.is_(None),
                        VisitOutboxEvent.claimed_until <= now,
                    ),
                )
                .order_by(VisitOutboxEvent.created_at, VisitOutboxEvent.event_id)
                .limit(1)
                .with_for_update(skip_locked=True)
                .scalar_subquery()
            )
            result = await self._session.execute(
                update(VisitOutboxEvent)
                .where(VisitOutboxEvent.event_id == pending_event)
                .values(claim_token=token, claimed_until=now + timedelta(seconds=30))
                .returning(VisitOutboxEvent.event_id, VisitOutboxEvent.payload)
                .execution_options(synchronize_session=False)
            )
            event = result.one_or_none()
            if event is None:
                return None
            return OutboxClaim(event.event_id, token, event.payload)

    @staticmethod
    def _owned_event(claim: OutboxClaim) -> Update:
        return update(VisitOutboxEvent).where(
            VisitOutboxEvent.event_id == claim.event_id,
            VisitOutboxEvent.claim_token == claim.token,
            VisitOutboxEvent.published_at.is_(None),
        )

    async def mark_published(self, claim: OutboxClaim) -> None:
        async with self.transaction():
            await self._session.execute(
                self._owned_event(claim).values(
                    published_at=datetime.now(UTC), claim_token=None, claimed_until=None
                )
            )

    async def release_claim(self, claim: OutboxClaim) -> None:
        async with self.transaction():
            await self._session.execute(
                self._owned_event(claim).values(claim_token=None, claimed_until=None)
            )
