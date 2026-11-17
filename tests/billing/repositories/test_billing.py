from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.models.billing import (
    BillingRecord,
    BillingStatus,
    ProcessedBillingEvent,
)
from app.billing.repositories.billing import BillingRepository
from app.billing.services.billing import BillingService
from app.common.events import VisitCompleted


@pytest.fixture
def event() -> VisitCompleted:
    return VisitCompleted(
        visit_id=2,
        start_date_time=datetime(2026, 11, 16, 9, tzinfo=UTC),
        end_date_time=datetime(2026, 11, 16, 10, 30, tzinfo=UTC),
        rate=Decimal("200.00"),
    )


async def test_duplicate_delivery_creates_one_record(
    db_session: AsyncSession, event: VisitCompleted
) -> None:
    service = BillingService(BillingRepository(db_session))
    await service.process_visit_completed(event)
    await service.process_visit_completed(event)

    record = await db_session.scalar(
        select(BillingRecord).where(BillingRecord.visit_id == event.visit_id)
    )
    assert record is not None
    assert record.amount == Decimal("300.00")
    assert record.status == BillingStatus.CREATED
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(BillingRecord)
            .where(BillingRecord.visit_id == event.visit_id)
        )
        == 1
    )
    assert await db_session.get(ProcessedBillingEvent, event.event_id) is not None


async def test_different_events_for_same_visit_create_one_record(
    db_session: AsyncSession, event: VisitCompleted
) -> None:
    service = BillingService(BillingRepository(db_session))
    await service.process_visit_completed(event)
    second_event = event.model_copy(update={"event_id": uuid4()})
    await service.process_visit_completed(second_event)

    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(BillingRecord)
            .where(BillingRecord.visit_id == event.visit_id)
        )
        == 1
    )
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(ProcessedBillingEvent)
            .where(
                ProcessedBillingEvent.event_id.in_(
                    [event.event_id, second_event.event_id]
                )
            )
        )
        == 2
    )


async def test_failed_processing_can_be_retried(
    db_session: AsyncSession, event: VisitCompleted, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = BillingRepository(db_session)
    with monkeypatch.context() as patch:
        patch.setattr(
            repository,
            "create_bill",
            AsyncMock(side_effect=SQLAlchemyError("Database unavailable")),
        )
        with pytest.raises(SQLAlchemyError, match="Database unavailable"):
            await BillingService(repository).process_visit_completed(event)

    assert await db_session.get(ProcessedBillingEvent, event.event_id) is None
    await db_session.rollback()
    await BillingService(repository).process_visit_completed(event)
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(BillingRecord)
            .where(BillingRecord.visit_id == event.visit_id)
        )
        == 1
    )


async def test_negative_amount_rolls_back_billing_and_event(
    db_session: AsyncSession, event: VisitCompleted
) -> None:
    # Bypass event deserialization to verify service validation independently.
    invalid_event = event.model_copy(update={"rate": Decimal("-200.00")})
    service = BillingService(BillingRepository(db_session))

    with pytest.raises(ValueError, match="Billing amount must be non-negative"):
        await service.process_visit_completed(invalid_event)

    assert await db_session.get(ProcessedBillingEvent, event.event_id) is None
    assert (
        await db_session.scalar(
            select(BillingRecord).where(BillingRecord.visit_id == event.visit_id)
        )
        is None
    )


async def test_replaying_processed_event_does_not_recreate_reversed_record(
    db_session: AsyncSession, event: VisitCompleted
) -> None:
    service = BillingService(BillingRepository(db_session))
    await service.process_visit_completed(event)
    await db_session.execute(
        update(BillingRecord)
        .where(BillingRecord.visit_id == event.visit_id)
        .values(status=BillingStatus.REVERSED)
    )
    await db_session.commit()

    await service.process_visit_completed(event)

    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(BillingRecord)
            .where(BillingRecord.visit_id == event.visit_id)
        )
        == 1
    )
    assert (
        await db_session.scalar(
            select(BillingRecord.status).where(BillingRecord.visit_id == event.visit_id)
        )
        == BillingStatus.REVERSED
    )


async def test_database_enforces_one_active_record_per_visit(
    db_session: AsyncSession,
) -> None:
    db_session.add(BillingRecord(visit_id=987654, amount=Decimal("10.00")))
    await db_session.commit()

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(BillingRecord(visit_id=987654, amount=Decimal("20.00")))
            await db_session.flush()


async def test_reversed_records_allow_a_new_active_bill(
    db_session: AsyncSession, event: VisitCompleted
) -> None:
    service = BillingService(BillingRepository(db_session))
    await service.process_visit_completed(event)
    await db_session.execute(
        update(BillingRecord)
        .where(BillingRecord.visit_id == event.visit_id)
        .values(status=BillingStatus.REVERSED)
    )
    await db_session.commit()

    # Replaying the original event is still deduplicated; a new event may bill again.
    await service.process_visit_completed(event)
    await service.process_visit_completed(
        event.model_copy(update={"event_id": uuid4()})
    )
    records = (
        await db_session.scalars(
            select(BillingRecord).where(BillingRecord.visit_id == event.visit_id)
        )
    ).all()
    assert sorted(record.status for record in records) == [
        BillingStatus.CREATED,
        BillingStatus.REVERSED,
    ]


async def test_database_rejects_negative_amount(db_session: AsyncSession) -> None:
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(BillingRecord(visit_id=987654, amount=Decimal("-0.01")))
            await db_session.flush()
