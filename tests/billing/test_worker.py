from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from unittest.mock import AsyncMock, create_autospec

import pytest
from faststream.kafka import TestKafkaBroker as KafkaTestBroker
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection, async_sessionmaker

from app.billing.models.billing import BillingRecord, ProcessedBillingEvent
from app.billing.services.base import BaseBillingService
from app.billing.worker import consume_visit_completed, create_broker
from app.common.events import VisitCompleted
from app.common.setting.config import Config
from app.visits.outbox import KafkaEventPublisher


@pytest.fixture
def completed_event() -> VisitCompleted:
    return VisitCompleted(
        visit_id=91827,
        start_date_time=datetime(2026, 11, 16, 9, tzinfo=UTC),
        end_date_time=datetime(2026, 11, 16, 10, 30, tzinfo=UTC),
        rate=Decimal("200.00"),
    )


@pytest.fixture
def worker_settings() -> Config:
    return Config(
        _env_file=None,
        postgres_host="localhost",
        postgres_port=5432,
        postgres_user="postgres",
        postgres_password=SecretStr("test"),
        postgres_db="jiris_health_test",
        event_retry_interval=0.001,
    )


async def test_publisher_to_consumer_creates_one_bill_for_duplicate_event(
    db_connection: AsyncConnection,
    worker_settings: Config,
    completed_event: VisitCompleted,
) -> None:
    sessions = async_sessionmaker(
        bind=db_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    broker = create_broker(worker_settings, sessions)
    async with KafkaTestBroker(broker):
        publisher = KafkaEventPublisher(
            broker, worker_settings.kafka_visit_completed_topic
        )
        await publisher.publish_completed(completed_event)
        await publisher.publish_completed(completed_event)

    assert (
        await db_connection.scalar(select(func.count()).select_from(BillingRecord)) == 1
    )
    assert await db_connection.scalar(select(BillingRecord.amount)) == Decimal("300.00")
    assert (
        await db_connection.scalar(select(ProcessedBillingEvent.event_id))
        == completed_event.event_id
    )


@pytest.mark.parametrize(
    "payload", [b"{broken-json", b'{"visit_id": -1}', b"null", b"[]", b"\xff"]
)
async def test_invalid_messages_do_not_block_the_next_valid_event(
    db_connection: AsyncConnection,
    worker_settings: Config,
    completed_event: VisitCompleted,
    payload: bytes,
    caplog: pytest.LogCaptureFixture,
) -> None:
    sessions = async_sessionmaker(
        bind=db_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    broker = create_broker(worker_settings, sessions)
    async with KafkaTestBroker(broker):
        await broker.publish(payload, topic=worker_settings.kafka_visit_completed_topic)
        assert (
            await db_connection.scalar(
                select(func.count()).select_from(ProcessedBillingEvent)
            )
            == 0
        )
        await KafkaEventPublisher(broker).publish_completed(completed_event)

    assert "Discarding invalid VisitCompleted message" in caplog.text
    assert (
        await db_connection.scalar(select(func.count()).select_from(BillingRecord)) == 1
    )


async def test_processing_failure_waits_before_retry(
    completed_event: VisitCompleted,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = create_autospec(BaseBillingService, instance=True)
    service.process_visit_completed.side_effect = ConnectionError(
        "Database unavailable"
    )
    sleep = AsyncMock()
    monkeypatch.setattr("app.billing.worker.asyncio.sleep", sleep)

    with pytest.raises(ConnectionError, match="Database unavailable"):
        await consume_visit_completed(
            completed_event.model_dump_json().encode(),
            cast(BaseBillingService, service),
            5,
        )

    sleep.assert_awaited_once_with(5)
