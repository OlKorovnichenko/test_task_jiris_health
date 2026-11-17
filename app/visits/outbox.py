import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import uuid4

from faststream.kafka import KafkaBroker
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.database.session import dispose_database, get_database
from app.common.events import VisitCompleted
from app.common.setting.config import get_settings
from app.visits.models.outbox import VisitOutboxEvent

logger = logging.getLogger(__name__)


class EventPublisher(Protocol):
    async def publish_completed(self, event: VisitCompleted) -> None: ...


class KafkaEventPublisher:
    def __init__(self, broker: KafkaBroker, topic: str = "visits.completed.v1") -> None:
        self._broker = broker
        self._topic = topic

    async def publish_completed(self, event: VisitCompleted) -> None:
        await self._broker.publish(
            event.model_dump(mode="json"),
            topic=self._topic,
            key=str(event.visit_id).encode(),
            correlation_id=str(event.event_id),
        )


async def publish_next(session: AsyncSession, publisher: EventPublisher) -> bool:
    token = uuid4()
    now = datetime.now(UTC)
    async with session.begin():
        event = await session.scalar(
            select(VisitOutboxEvent)
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
        )
        if event is None:
            return False
        event.claim_token = token
        event.claimed_until = now + timedelta(seconds=30)
        event_id, payload = event.event_id, event.payload

    owned_event = update(VisitOutboxEvent).where(
        VisitOutboxEvent.event_id == event_id,
        VisitOutboxEvent.claim_token == token,
        VisitOutboxEvent.published_at.is_(None),
    )
    try:
        await asyncio.wait_for(
            publisher.publish_completed(VisitCompleted.model_validate(payload)),
            timeout=10,
        )
        async with session.begin():
            await session.execute(
                owned_event.values(
                    published_at=datetime.now(UTC), claim_token=None, claimed_until=None
                )
            )
    except Exception:
        async with session.begin():
            await session.execute(
                owned_event.values(claim_token=None, claimed_until=None)
            )
        raise
    return True


async def run() -> None:
    settings = get_settings()
    session_factory = get_database().sessions
    try:
        while True:
            try:
                async with KafkaBroker(
                    settings.kafka_bootstrap_servers,
                    acks="all",
                    enable_idempotence=True,
                    request_timeout_ms=10000,
                ) as broker:
                    publisher = KafkaEventPublisher(
                        broker, settings.kafka_visit_completed_topic
                    )
                    while True:
                        async with session_factory() as session:
                            published = await publish_next(session, publisher)
                        if not published:
                            await asyncio.sleep(settings.outbox_poll_interval)
            except Exception:
                logger.exception("Outbox publication failed; retrying automatically")
                await asyncio.sleep(settings.event_retry_interval)
    finally:
        await dispose_database()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
