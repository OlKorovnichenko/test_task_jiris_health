from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.visits.models.visits import Visit
from app.visits.repositories.visits import VisitRepository
from app.visits.utils.enumerations.visit_enums import VisitStatus


async def test_get_for_update_returns_visit(
    db_session: AsyncSession, visits: dict[VisitStatus, int]
) -> None:
    repository = VisitRepository(db_session)

    visit = await repository.get_for_update(visits[VisitStatus.IN_PROGRESS])

    assert isinstance(visit, Visit)
    assert visit.id == visits[VisitStatus.IN_PROGRESS]
    assert visit.status == VisitStatus.IN_PROGRESS
    assert await db_session.get(Visit, visits[VisitStatus.IN_PROGRESS]) is visit


async def test_get_for_update_returns_none_for_missing_visit(
    db_session: AsyncSession, visits: dict[VisitStatus, int]
) -> None:
    repository = VisitRepository(db_session)

    assert await repository.get_for_update(999999) is None


async def test_loaded_visit_changes_are_tracked(
    db_session: AsyncSession,
    db_connection: AsyncConnection,
    visits: dict[VisitStatus, int],
) -> None:
    repository = VisitRepository(db_session)
    visit = await repository.get_for_update(visits[VisitStatus.IN_PROGRESS])
    assert visit is not None

    visit.status = VisitStatus.COMPLETED
    await db_session.commit()

    status = await db_connection.scalar(
        select(Visit.status).where(Visit.id == visits[VisitStatus.IN_PROGRESS])
    )
    assert status == VisitStatus.COMPLETED


async def test_get_for_update_leaves_transaction_to_caller(
    db_session: AsyncSession, visits: dict[VisitStatus, int]
) -> None:
    await VisitRepository(db_session).get_for_update(visits[VisitStatus.IN_PROGRESS])

    assert db_session.in_transaction()
