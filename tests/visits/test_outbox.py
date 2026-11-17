from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import delete, event, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.common.events import VisitCompleted
from app.visits.models.outbox import VisitOutboxEvent
from app.visits.models.visits import Visit
from app.visits.outbox import publish_next
from app.visits.repositories.visits import VisitRepository
from app.visits.services.visits import VisitService
from app.visits.utils.enumerations.visit_enums import VisitStatus


@pytest_asyncio.fixture
async def pending_event(db_session: AsyncSession) -> AsyncIterator[None]:
    await db_session.execute(delete(VisitOutboxEvent))
    await db_session.commit()
    await VisitService(VisitRepository(db_session)).complete(2)
    yield


async def test_marks_published_after_confirmation(
    pending_event: None, db_session: AsyncSession, db_connection: AsyncConnection
) -> None:
    publisher = AsyncMock()

    assert await publish_next(db_session, publisher)
    assert not await publish_next(db_session, publisher)

    publisher.publish_completed.assert_awaited_once()
    published = publisher.publish_completed.call_args.args[0]
    assert isinstance(published, VisitCompleted)
    assert published.visit_id == 2
    assert await db_connection.scalar(select(VisitOutboxEvent.published_at)) is not None


async def test_broker_failure_keeps_event_for_retry(
    pending_event: None, db_session: AsyncSession, db_connection: AsyncConnection
) -> None:
    publisher = AsyncMock()
    publisher.publish_completed.side_effect = ConnectionError("Kafka unavailable")

    with pytest.raises(ConnectionError, match="Kafka unavailable"):
        await publish_next(db_session, publisher)

    assert await db_connection.scalar(select(VisitOutboxEvent.published_at)) is None
    assert (
        await db_connection.scalar(select(Visit.status).where(Visit.id == 2))
        == VisitStatus.COMPLETED
    )

    publisher.publish_completed.side_effect = None
    assert await publish_next(db_session, publisher)
    attempts = publisher.publish_completed.call_args_list
    assert attempts[0].args[0].event_id == attempts[1].args[0].event_id


async def test_commit_failure_after_publication_redelivers_same_event(
    pending_event: None, db_session: AsyncSession, db_connection: AsyncConnection
) -> None:
    publisher = AsyncMock()

    def fail_commit(session: object) -> None:
        raise SQLAlchemyError("Commit failed after publish")

    event.listen(db_session.sync_session, "before_commit", fail_commit, once=True)
    with pytest.raises(SQLAlchemyError, match="Commit failed after publish"):
        await publish_next(db_session, publisher)

    assert await db_connection.scalar(select(VisitOutboxEvent.published_at)) is None
    assert await publish_next(db_session, publisher)
    attempts = publisher.publish_completed.call_args_list
    assert attempts[0].args[0].event_id == attempts[1].args[0].event_id


async def test_completion_failure_rolls_back_status_and_event(
    db_session: AsyncSession, db_connection: AsyncConnection
) -> None:
    def fail_commit(session: object) -> None:
        raise SQLAlchemyError("Commit failed")

    event.listen(db_session.sync_session, "before_commit", fail_commit, once=True)
    with pytest.raises(HTTPException) as error:
        await VisitService(VisitRepository(db_session)).complete(2)

    assert error.value.status_code == 500

    assert (
        await db_connection.scalar(select(Visit.status).where(Visit.id == 2))
        == VisitStatus.IN_PROGRESS
    )
    assert (
        await db_connection.scalar(
            select(VisitOutboxEvent.event_id).where(VisitOutboxEvent.visit_id == 2)
        )
        is None
    )
