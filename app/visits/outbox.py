import asyncio
import logging
from typing import Protocol

from faststream.kafka import KafkaBroker
from pydantic import ValidationError

from app.common.database.session import dispose_database, get_database
from app.common.events import VisitCompleted
from app.common.setting.config import get_settings
from app.visits.repositories.base import BaseOutboxRepository
from app.visits.repositories.outbox import OutboxRepository

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


async def publish_next(
    repository: BaseOutboxRepository, publisher: EventPublisher
) -> bool:
    claim = await repository.claim_next_pending()
    if claim is None:
        return False
    try:
        event = VisitCompleted.model_validate(claim.payload)
    except ValidationError:
        logger.exception(
            f"Invalid outbox payload for event {claim.event_id}; retry after lease expiry"
        )
        return True

    try:
        await asyncio.wait_for(
            publisher.publish_completed(event),
            timeout=10,
        )
        await repository.mark_published(claim)
    except Exception:
        try:
            await repository.release_claim(claim)
        except Exception:
            logger.warning(
                f"Failed to release outbox claim for {claim.event_id}", exc_info=True
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
                            handled = await publish_next(
                                OutboxRepository(session), publisher
                            )
                        if not handled:
                            await asyncio.sleep(settings.outbox_poll_interval)
            except Exception:
                logger.exception("Outbox publication failed; retrying automatically")
                await asyncio.sleep(settings.event_retry_interval)
    finally:
        await dispose_database()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
