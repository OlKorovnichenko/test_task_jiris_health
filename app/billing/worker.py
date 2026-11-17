import asyncio
import logging

from faststream import AckPolicy, FastStream
from faststream.kafka import KafkaBroker

from app.billing.repositories.billing import BillingRepository
from app.billing.services.billing import BillingService
from app.common.database.session import engine, session_factory
from app.common.events import VisitCompleted
from app.common.setting.config import settings

logger = logging.getLogger(__name__)
broker = KafkaBroker(settings.kafka_bootstrap_servers)
app = FastStream(broker)


@broker.subscriber(
    settings.kafka_visit_completed_topic,
    group_id=settings.kafka_billing_group,
    auto_offset_reset="earliest",
    ack_policy=AckPolicy.NACK_ON_ERROR,
    max_workers=1,
    max_poll_records=1,
)
async def on_visit_completed(event: VisitCompleted) -> None:
    try:
        async with session_factory() as session:
            await BillingService(BillingRepository(session)).process_visit_completed(
                event
            )
    except Exception:
        await asyncio.sleep(settings.event_retry_interval)
        raise


async def run() -> None:
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
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
