import pytest
from httpx import AsyncClient
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.common.events import VisitCompleted
from app.visits.models.outbox import VisitOutboxEvent
from app.visits.models.visits import Visit
from app.visits.repositories.visits import VisitRepository
from app.visits.utils.enumerations.visit_enums import VisitStatus


async def test_complete_visit(
    client: AsyncClient, db_connection: AsyncConnection, visits: dict[VisitStatus, int]
) -> None:
    visit_id = visits[VisitStatus.IN_PROGRESS]
    response = await client.post(f"/api/visits/{visit_id}/complete")

    assert response.status_code == 200
    assert response.json() == {"id": visit_id, "status": "Completed"}
    status = await db_connection.scalar(
        select(Visit.status).where(Visit.id == visit_id)
    )
    assert status == VisitStatus.COMPLETED
    payload = await db_connection.scalar(
        select(VisitOutboxEvent.payload).where(VisitOutboxEvent.visit_id == visit_id)
    )
    event = VisitCompleted.model_validate(payload)
    assert event.visit_id == visit_id
    assert event.rate == 200


@pytest.mark.parametrize(
    ("visit_status", "detail"),
    [
        (VisitStatus.SCHEDULED, "Visit not started yet"),
        (VisitStatus.COMPLETED, "Visit already completed"),
        (VisitStatus.CANCELED, "Visit already canceled"),
        (VisitStatus.MISSED, "Visit already missed"),
    ],
)
async def test_rejects_invalid_status(
    client: AsyncClient,
    db_connection: AsyncConnection,
    visit_status: VisitStatus,
    detail: str,
    visits: dict[VisitStatus, int],
) -> None:
    visit_id = visits[visit_status]
    query = select(Visit.status).where(Visit.id == visit_id)
    original_status = await db_connection.scalar(query)

    response = await client.post(f"/api/visits/{visit_id}/complete")

    assert response.status_code == 409
    assert response.json() == {"detail": detail}
    assert await db_connection.scalar(query) == original_status


async def test_missing_visit(client: AsyncClient) -> None:
    response = await client.post("/api/visits/999999/complete")

    assert response.status_code == 404
    assert response.json() == {"detail": "Visit not found"}


async def test_database_failure_returns_500_and_rolls_back(
    client: AsyncClient,
    db_connection: AsyncConnection,
    monkeypatch: pytest.MonkeyPatch,
    visits: dict[VisitStatus, int],
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fail_commit(session: object) -> None:
        raise SQLAlchemyError("Commit failed")

    def install_failure(session: AsyncSession) -> None:
        event.listen(session.sync_session, "before_commit", fail_commit, once=True)

    original_init = VisitRepository.__init__

    def failing_init(self: VisitRepository, session: AsyncSession) -> None:
        original_init(self, session)
        install_failure(session)

    monkeypatch.setattr(VisitRepository, "__init__", failing_init)

    visit_id = visits[VisitStatus.IN_PROGRESS]
    response = await client.post(f"/api/visits/{visit_id}/complete")

    assert "Failed to complete visit" in caplog.text
    assert any(record.exc_info for record in caplog.records)
    assert response.status_code == 500
    assert response.json() == {"detail": "Failed to complete visit"}
    assert (
        await db_connection.scalar(select(Visit.status).where(Visit.id == visit_id))
        == VisitStatus.IN_PROGRESS
    )
    assert (
        await db_connection.scalar(
            select(VisitOutboxEvent.event_id).where(
                VisitOutboxEvent.visit_id == visit_id
            )
        )
        is None
    )


@pytest.mark.parametrize("visit_id", ["not-an-integer", "0", "-1"])
async def test_invalid_visit_id(client: AsyncClient, visit_id: str) -> None:
    response = await client.post(f"/api/visits/{visit_id}/complete")

    assert response.status_code == 422


async def test_repeated_completion(
    client: AsyncClient, visits: dict[VisitStatus, int]
) -> None:
    visit_id = visits[VisitStatus.IN_PROGRESS]
    first = await client.post(f"/api/visits/{visit_id}/complete")
    second = await client.post(f"/api/visits/{visit_id}/complete")

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json() == {"detail": "Visit already completed"}


async def test_requests_use_separate_sessions(
    client: AsyncClient,
    request_sessions: list[AsyncSession],
    visits: dict[VisitStatus, int],
) -> None:
    await client.post(f"/api/visits/{visits[VisitStatus.IN_PROGRESS]}/complete")
    await client.post("/api/visits/999999/complete")

    assert len(request_sessions) == 2
    assert request_sessions[0] is not request_sessions[1]
    assert all(not session.in_transaction() for session in request_sessions)
