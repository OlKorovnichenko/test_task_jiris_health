import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.visits.models.visits import Visit
from app.visits.utils.enumerations.visit_enums import VisitStatus


async def test_complete_visit(
    client: AsyncClient, db_connection: AsyncConnection
) -> None:
    response = await client.post("/api/visits/2/complete")

    assert response.status_code == 200
    assert response.json() == {"id": 2, "status": "Completed"}
    status = await db_connection.scalar(select(Visit.status).where(Visit.id == 2))
    assert status == VisitStatus.COMPLETED


@pytest.mark.parametrize(
    ("visit_id", "detail"),
    [
        (1, "Visit not started yet"),
        (3, "Visit already completed"),
        (4, "Visit already cancelled"),
        (5, "Visit already missed"),
    ],
)
async def test_rejects_invalid_status(
    client: AsyncClient,
    db_connection: AsyncConnection,
    visit_id: int,
    detail: str,
) -> None:
    query = select(Visit.status).where(Visit.id == visit_id)
    original_status = await db_connection.scalar(query)

    response = await client.post(f"/api/visits/{visit_id}/complete")

    assert response.status_code == 400
    assert response.json() == {"detail": detail}
    assert await db_connection.scalar(query) == original_status


async def test_missing_visit(client: AsyncClient) -> None:
    response = await client.post("/api/visits/999999/complete")

    assert response.status_code == 404
    assert response.json() == {"detail": "Visit not found"}


async def test_invalid_visit_id(client: AsyncClient) -> None:
    response = await client.post("/api/visits/not-an-integer/complete")

    assert response.status_code == 422


async def test_repeated_completion(client: AsyncClient) -> None:
    first = await client.post("/api/visits/2/complete")
    second = await client.post("/api/visits/2/complete")

    assert first.status_code == 200
    assert second.status_code == 400
    assert second.json() == {"detail": "Visit already completed"}


async def test_requests_use_separate_sessions(
    client: AsyncClient, request_sessions: list[AsyncSession]
) -> None:
    await client.post("/api/visits/2/complete")
    await client.post("/api/visits/999999/complete")

    assert len(request_sessions) == 2
    assert request_sessions[0] is not request_sessions[1]
    assert all(not session.in_transaction() for session in request_sessions)
