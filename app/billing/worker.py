import asyncio
import logging

from faststream import AckPolicy, FastStream
from faststream.kafka import KafkaBroker
from faststream.kafka.message import KafkaMessage
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.billing.repositories.billing import BillingRepository
from app.billing.services.base import BaseBillingService
from app.billing.services.billing import BillingService
from app.common.database.session import dispose_database, get_database
from app.common.events import VisitCompleted
from app.common.setting.config import Config, get_settings

logger = logging.getLogger(__name__)


async def consume_visit_completed(
    payload: bytes, service: BaseBillingService, retry_interval: float
) -> None:
    try:
        event = VisitCompleted.model_validate_json(payload)
    except ValidationError:
        logger.error(f"Discarding invalid VisitCompleted message: {payload[:200]!r}")
        return

    try:
        await service.process_visit_completed(event)
    except Exception:
        logger.exception(
            "Billing processing failed for event %s; retrying", event.event_id
        )
        await asyncio.sleep(retry_interval)
        raise


async def raw_payload(message: KafkaMessage) -> bytes:
    return bytes(message.body)


def create_broker(
    settings: Config, sessions: async_sessionmaker[AsyncSession]
) -> KafkaBroker:
    broker = KafkaBroker(settings.kafka_bootstrap_servers)

    @broker.subscriber(
        settings.kafka_visit_completed_topic,
        group_id=settings.kafka_billing_group,
        auto_offset_reset="earliest",
        ack_policy=AckPolicy.NACK_ON_ERROR,
        decoder=raw_payload,
        max_workers=1,
        max_poll_records=1,
    )
    async def on_visit_completed(payload: bytes) -> None:
        async with sessions() as session:
            await consume_visit_completed(
                payload,
                BillingService(BillingRepository(session)),
                settings.event_retry_interval,
            )

    return broker


async def run() -> None:
    settings = get_settings()
    broker = create_broker(settings, get_database().sessions)
    app = FastStream(broker)
    try:
        while True:
            try:
                await app.run()
                return
            except Exception:
                logger.exception("Billing worker failed")
                await broker.stop()
                await asyncio.sleep(settings.event_retry_interval)
    finally:
        await dispose_database()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
