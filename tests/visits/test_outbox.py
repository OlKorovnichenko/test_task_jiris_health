from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import event, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.common.events import VisitCompleted
from app.visits.exceptions import VisitCompletionError
from app.visits.models.outbox import VisitOutboxEvent
from app.visits.models.visits import Visit
from app.visits.outbox import publish_next
from app.visits.repositories.outbox import OutboxRepository
from app.visits.repositories.visits import VisitRepository
from app.visits.services.visits import VisitService
from app.visits.utils.enumerations.visit_enums import VisitStatus


@pytest_asyncio.fixture
async def pending_event(
    db_session: AsyncSession, visits: dict[VisitStatus, int]
) -> VisitCompleted:
    await VisitService(VisitRepository(db_session)).complete(
        visits[VisitStatus.IN_PROGRESS]
    )
    payload = await db_session.scalar(
        select(VisitOutboxEvent.payload).where(
            VisitOutboxEvent.visit_id == visits[VisitStatus.IN_PROGRESS]
        )
    )
    await db_session.commit()
    return VisitCompleted.model_validate(payload)


async def test_marks_published_after_confirmation_without_open_transaction(
    pending_event: VisitCompleted,
    db_session: AsyncSession,
    db_connection: AsyncConnection,
) -> None:
    async def publish(completed: VisitCompleted) -> None:
        assert not db_session.in_transaction()
        assert completed.event_id == pending_event.event_id
        assert await db_connection.scalar(select(VisitOutboxEvent.published_at)) is None

    publisher = AsyncMock()
    publisher.publish_completed.side_effect = publish
    assert await publish_next(OutboxRepository(db_session), publisher)
    assert not await publish_next(OutboxRepository(db_session), publisher)
    publisher.publish_completed.assert_awaited_once()
    assert await db_connection.scalar(select(VisitOutboxEvent.published_at)) is not None


async def test_broker_failure_keeps_event_for_retry(
    pending_event: VisitCompleted,
    db_session: AsyncSession,
    db_connection: AsyncConnection,
) -> None:
    publisher = AsyncMock()
    publisher.publish_completed.side_effect = ConnectionError("Kafka unavailable")

    with pytest.raises(ConnectionError, match="Kafka unavailable"):
        await publish_next(OutboxRepository(db_session), publisher)

    assert await db_connection.scalar(select(VisitOutboxEvent.published_at)) is None
    assert await db_connection.scalar(select(VisitOutboxEvent.claim_token)) is None
    assert (
        await db_connection.scalar(
            select(Visit.status).where(Visit.id == pending_event.visit_id)
        )
        == VisitStatus.COMPLETED
    )

    publisher.publish_completed.side_effect = None
    assert await publish_next(OutboxRepository(db_session), publisher)
    attempts = publisher.publish_completed.call_args_list
    assert attempts[0].args[0].event_id == attempts[1].args[0].event_id


async def test_commit_failure_after_publication_redelivers_same_event(
    pending_event: VisitCompleted,
    db_session: AsyncSession,
    db_connection: AsyncConnection,
) -> None:
    def fail_commit(session: object) -> None:
        raise SQLAlchemyError("Commit failed after publish")

    async def publish(completed: VisitCompleted) -> None:
        event.listen(db_session.sync_session, "before_commit", fail_commit, once=True)

    publisher = AsyncMock()
    publisher.publish_completed.side_effect = publish
    with pytest.raises(SQLAlchemyError, match="Commit failed after publish"):
        await publish_next(OutboxRepository(db_session), publisher)

    assert await db_connection.scalar(select(VisitOutboxEvent.published_at)) is None
    publisher.publish_completed.side_effect = None
    assert await publish_next(OutboxRepository(db_session), publisher)
    attempts = publisher.publish_completed.call_args_list
    assert attempts[0].args[0].event_id == attempts[1].args[0].event_id


async def test_failed_claim_release_preserves_original_error_and_recovers_after_expiry(
    pending_event: VisitCompleted,
    db_session: AsyncSession,
    db_connection: AsyncConnection,
    caplog: pytest.LogCaptureFixture,
) -> None:
    attempts = 0

    def fail_commits(session: object) -> None:
        nonlocal attempts
        attempts += 1
        raise SQLAlchemyError(f"Commit failed {attempts}")

    async def publish(completed: VisitCompleted) -> None:
        event.listen(db_session.sync_session, "before_commit", fail_commits)

    publisher = AsyncMock()
    publisher.publish_completed.side_effect = publish
    try:
        with pytest.raises(SQLAlchemyError, match="Commit failed 1"):
            await publish_next(OutboxRepository(db_session), publisher)
    finally:
        event.remove(db_session.sync_session, "before_commit", fail_commits)

    assert attempts == 2
    assert "Failed to release outbox claim" in caplog.text
    assert await db_connection.scalar(select(VisitOutboxEvent.published_at)) is None
    assert await db_connection.scalar(select(VisitOutboxEvent.claim_token)) is not None
    assert not await publish_next(OutboxRepository(db_session), publisher)

    async with db_session.begin():
        await db_session.execute(
            update(VisitOutboxEvent)
            .where(VisitOutboxEvent.event_id == pending_event.event_id)
            .values(claimed_until=datetime.now(UTC) - timedelta(seconds=1))
        )
    publisher.publish_completed.side_effect = None
    assert await publish_next(OutboxRepository(db_session), publisher)
    assert publisher.publish_completed.await_count == 2


async def test_invalid_payload_keeps_lease_and_allows_newer_event_to_publish(
    pending_event: VisitCompleted,
    db_session: AsyncSession,
    db_connection: AsyncConnection,
    visits: dict[VisitStatus, int],
    caplog: pytest.LogCaptureFixture,
) -> None:
    async with db_session.begin():
        await db_session.execute(
            update(VisitOutboxEvent)
            .where(VisitOutboxEvent.event_id == pending_event.event_id)
            .values(
                payload={"visit_id": -1},
                created_at=datetime.now(UTC) - timedelta(minutes=1),
            )
        )
        await db_session.execute(
            update(Visit)
            .where(Visit.id == visits[VisitStatus.SCHEDULED])
            .values(status=VisitStatus.IN_PROGRESS)
        )
    await VisitService(VisitRepository(db_session)).complete(
        visits[VisitStatus.SCHEDULED]
    )

    publisher = AsyncMock()
    assert await publish_next(OutboxRepository(db_session), publisher)
    publisher.publish_completed.assert_not_awaited()
    assert str(pending_event.event_id) in caplog.text
    claimed_until = await db_connection.scalar(
        select(VisitOutboxEvent.claimed_until).where(
            VisitOutboxEvent.event_id == pending_event.event_id
        )
    )
    assert claimed_until is not None
    assert claimed_until > datetime.now(UTC)

    assert await publish_next(OutboxRepository(db_session), publisher)
    assert (
        publisher.publish_completed.call_args.args[0].visit_id
        == visits[VisitStatus.SCHEDULED]
    )
    assert not await publish_next(OutboxRepository(db_session), publisher)
    assert (
        await db_connection.scalar(
            select(VisitOutboxEvent.published_at).where(
                VisitOutboxEvent.event_id == pending_event.event_id
            )
        )
        is None
    )

    async with db_session.begin():
        await db_session.execute(
            update(VisitOutboxEvent)
            .where(VisitOutboxEvent.event_id == pending_event.event_id)
            .values(
                payload=pending_event.model_dump(mode="json"),
                claimed_until=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
    assert await publish_next(OutboxRepository(db_session), publisher)
    assert (
        publisher.publish_completed.call_args.args[0].event_id == pending_event.event_id
    )


async def test_worker_crash_lease_expires_and_event_is_retried(
    pending_event: VisitCompleted, db_session: AsyncSession
) -> None:
    async with db_session.begin():
        await db_session.execute(
            update(VisitOutboxEvent)
            .where(VisitOutboxEvent.event_id == pending_event.event_id)
            .values(
                claim_token=uuid4(),
                claimed_until=datetime.now(UTC) + timedelta(seconds=30),
            )
        )
    publisher = AsyncMock()
    assert not await publish_next(OutboxRepository(db_session), publisher)
    publisher.publish_completed.assert_not_awaited()

    async with db_session.begin():
        await db_session.execute(
            update(VisitOutboxEvent)
            .where(VisitOutboxEvent.event_id == pending_event.event_id)
            .values(claimed_until=datetime.now(UTC) - timedelta(seconds=1))
        )
    assert await publish_next(OutboxRepository(db_session), publisher)
    assert (
        publisher.publish_completed.call_args.args[0].event_id == pending_event.event_id
    )


async def test_expired_owner_cannot_acknowledge_another_workers_claim(
    pending_event: VisitCompleted,
    db_session: AsyncSession,
    db_connection: AsyncConnection,
) -> None:
    replacement_token = uuid4()

    async def replace_claim(completed: VisitCompleted) -> None:
        await db_connection.execute(
            update(VisitOutboxEvent)
            .where(VisitOutboxEvent.event_id == pending_event.event_id)
            .values(
                claim_token=replacement_token,
                claimed_until=datetime.now(UTC) + timedelta(seconds=30),
            )
        )

    publisher = AsyncMock()
    publisher.publish_completed.side_effect = replace_claim
    await publish_next(OutboxRepository(db_session), publisher)
    assert await db_connection.scalar(select(VisitOutboxEvent.published_at)) is None
    assert (
        await db_connection.scalar(select(VisitOutboxEvent.claim_token))
        == replacement_token
    )


async def test_completion_failure_rolls_back_status_and_event(
    db_session: AsyncSession,
    db_connection: AsyncConnection,
    visits: dict[VisitStatus, int],
) -> None:
    def fail_commit(session: object) -> None:
        raise SQLAlchemyError("Commit failed")

    event.listen(db_session.sync_session, "before_commit", fail_commit, once=True)
    with pytest.raises(VisitCompletionError):
        await VisitService(VisitRepository(db_session)).complete(
            visits[VisitStatus.IN_PROGRESS]
        )

    assert (
        await db_connection.scalar(
            select(Visit.status).where(Visit.id == visits[VisitStatus.IN_PROGRESS])
        )
        == VisitStatus.IN_PROGRESS
    )
    assert await db_connection.scalar(select(VisitOutboxEvent.event_id)) is None
