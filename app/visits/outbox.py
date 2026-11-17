import asyncio
import logging
from datetime import UTC, datetime
from typing import Protocol

from faststream.kafka import KafkaBroker
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.database.session import engine, session_factory
from app.common.events import VisitCompleted
from app.common.setting.config import settings
from app.visits.models.outbox import VisitOutboxEvent

logger = logging.getLogger(__name__)


class EventPublisher(Protocol):
    async def publish_completed(self, event: VisitCompleted) -> None: ...


class KafkaEventPublisher:
    def __init__(self, broker: KafkaBroker) -> None:
        self._broker = broker

    async def publish_completed(self, event: VisitCompleted) -> None:
        await self._broker.publish(
            event.model_dump(mode="json"),
            topic=settings.kafka_visit_completed_topic,
            key=str(event.visit_id).encode(),
            correlation_id=str(event.event_id),
        )


async def publish_next(session: AsyncSession, publisher: EventPublisher) -> bool:
    async with session.begin():
        event = await session.scalar(
            select(VisitOutboxEvent)
            .where(VisitOutboxEvent.published_at.is_(None))
            .order_by(VisitOutboxEvent.created_at, VisitOutboxEvent.event_id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if event is None:
            return False
        await publisher.publish_completed(VisitCompleted.model_validate(event.payload))
        event.published_at = datetime.now(UTC)
    return True


async def run() -> None:
    try:
        while True:
            try:
                async with KafkaBroker(
                    settings.kafka_bootstrap_servers,
                    acks="all",
                    enable_idempotence=True,
                    request_timeout_ms=10000,
                ) as broker:
                    publisher = KafkaEventPublisher(broker)
                    while True:
                        async with session_factory() as session:
                            published = await publish_next(session, publisher)
                        if not published:
                            await asyncio.sleep(settings.outbox_poll_interval)
            except Exception:
                logger.exception("Outbox publication failed; retrying automatically")
                await asyncio.sleep(settings.event_retry_interval)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
