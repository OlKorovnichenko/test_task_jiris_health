import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.billing.models.billing import BillingRecord, ProcessedBillingEvent
from app.billing.repositories.billing import BillingRepository
from app.billing.services.billing import BillingService
from app.common.database.session import get_session
from app.common.events import VisitCompleted
from app.common.setting.config import get_settings
from app.main import app
from app.visits.models.outbox import VisitOutboxEvent
from app.visits.models.visits import Visit
from app.visits.utils.enumerations.visit_enums import VisitStatus


@pytest_asyncio.fixture
async def committed_visit() -> AsyncIterator[
    tuple[async_sessionmaker[AsyncSession], int]
]:
    # Row locks must be tested with independent connections and real commits.
    engine = create_async_engine(get_settings().postgres_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory.begin() as session:
        visit = Visit(
            start_date_time=datetime(2026, 11, 16, 9, tzinfo=UTC),
            end_date_time=datetime(2026, 11, 16, 10, 30, tzinfo=UTC),
            description="Concurrent billing test",
            rate=Decimal("200.00"),
            status=VisitStatus.IN_PROGRESS,
        )
        session.add(visit)
        await session.flush()
        visit_id = visit.id
    try:
        yield factory, visit_id
    finally:
        async with factory.begin() as session:
            outbox_ids = select(VisitOutboxEvent.event_id).where(
                VisitOutboxEvent.visit_id == visit_id
            )
            await session.execute(
                delete(ProcessedBillingEvent).where(
                    ProcessedBillingEvent.event_id.in_(outbox_ids)
                )
            )
            await session.execute(
                delete(BillingRecord).where(BillingRecord.visit_id == visit_id)
            )
            await session.execute(
                delete(VisitOutboxEvent).where(VisitOutboxEvent.visit_id == visit_id)
            )
            await session.execute(delete(Visit).where(Visit.id == visit_id))
        await engine.dispose()


async def test_two_concurrent_complete_requests_create_one_event_and_bill(
    committed_visit: tuple[async_sessionmaker[AsyncSession], int],
) -> None:
    factory, visit_id = committed_visit
    ready = asyncio.Event()
    sessions = []

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            sessions.append(session)
            if len(sessions) == 2:
                ready.set()
            await asyncio.wait_for(ready.wait(), timeout=5)
            yield session

    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_session] = override_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            responses = await asyncio.wait_for(
                asyncio.gather(
                    client.post(f"/api/visits/{visit_id}/complete"),
                    client.post(f"/api/visits/{visit_id}/complete"),
                ),
                timeout=10,
            )
        assert sorted(response.status_code for response in responses) == [200, 409]
        assert sessions[0] is not sessions[1]
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)

    async with factory() as session:
        payloads = (
            await session.scalars(
                select(VisitOutboxEvent.payload).where(
                    VisitOutboxEvent.visit_id == visit_id
                )
            )
        ).all()
    assert len(payloads) == 1
    event = VisitCompleted.model_validate(payloads[0])

    async def deliver() -> None:
        async with factory() as session:
            await BillingService(BillingRepository(session)).process_visit_completed(
                event
            )

    await asyncio.wait_for(asyncio.gather(deliver(), deliver()), timeout=10)

    async with factory() as session:
        records = (
            await session.scalars(
                select(BillingRecord).where(BillingRecord.visit_id == visit_id)
            )
        ).all()
        assert len(records) == 1
        assert records[0].amount == Decimal("300.00")
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProcessedBillingEvent)
                .where(ProcessedBillingEvent.event_id == event.event_id)
            )
            == 1
        )


async def test_concurrent_distinct_events_still_create_one_bill(
    committed_visit: tuple[async_sessionmaker[AsyncSession], int],
) -> None:
    factory, visit_id = committed_visit
    event_ids = [uuid4(), uuid4()]

    async def deliver(index: int) -> None:
        event = VisitCompleted(
            event_id=event_ids[index],
            visit_id=visit_id,
            start_date_time=datetime(2026, 11, 16, 9, tzinfo=UTC),
            end_date_time=datetime(2026, 11, 16, 10, 30, tzinfo=UTC),
            rate=Decimal("200.00"),
        )
        async with factory() as session:
            await BillingService(BillingRepository(session)).process_visit_completed(
                event
            )

    try:
        await asyncio.wait_for(asyncio.gather(deliver(0), deliver(1)), timeout=10)
        async with factory() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(BillingRecord)
                    .where(BillingRecord.visit_id == visit_id)
                )
                == 1
            )
    finally:
        async with factory.begin() as session:
            await session.execute(
                delete(ProcessedBillingEvent).where(
                    ProcessedBillingEvent.event_id.in_(event_ids)
                )
            )


async def test_concurrent_outbox_workers_publish_only_the_claimed_event(
    committed_visit: tuple[async_sessionmaker[AsyncSession], int],
) -> None:
    from unittest.mock import AsyncMock

    from app.visits.outbox import publish_next
    from app.visits.repositories.visits import VisitRepository
    from app.visits.services.visits import VisitService

    factory, visit_id = committed_visit
    async with factory() as session:
        await VisitService(VisitRepository(session)).complete(visit_id)

    publishing = asyncio.Event()
    release = asyncio.Event()

    async def publish(event: VisitCompleted) -> None:
        publishing.set()
        await asyncio.wait_for(release.wait(), timeout=5)

    publisher = AsyncMock()
    publisher.publish_completed.side_effect = publish

    async def run_first() -> bool:
        async with factory() as session:
            return await publish_next(session, publisher)

    first = asyncio.create_task(run_first())
    try:
        await asyncio.wait_for(publishing.wait(), timeout=5)
        async with factory() as session:
            # The row lock is already released while Kafka publication is pending.
            async with session.begin():
                assert (
                    await session.scalar(
                        select(VisitOutboxEvent)
                        .where(VisitOutboxEvent.visit_id == visit_id)
                        .with_for_update(nowait=True)
                    )
                    is not None
                )
            assert not await publish_next(session, publisher)
        release.set()
        assert await asyncio.wait_for(first, timeout=5)
        publisher.publish_completed.assert_awaited_once()
    finally:
        release.set()
        if not first.done():
            first.cancel()
        await asyncio.gather(first, return_exceptions=True)
