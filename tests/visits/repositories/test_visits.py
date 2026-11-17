from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.visits.models.visits import Visit
from app.visits.repositories.visits import VisitRepository
from app.visits.utils.enumerations.visit_enums import VisitStatus


async def test_get_one_returns_visit(db_session: AsyncSession) -> None:
    repository = VisitRepository(db_session)

    visit = await repository.get_one(2)

    assert isinstance(visit, Visit)
    assert visit.id == 2
    assert visit.status == VisitStatus.IN_PROGRESS
    assert await db_session.get(Visit, 2) is visit
    assert repository.session is db_session


async def test_get_one_returns_none_for_missing_visit(db_session: AsyncSession) -> None:
    repository = VisitRepository(db_session)

    assert await repository.get_one(999999) is None


async def test_loaded_visit_changes_are_tracked(
    db_session: AsyncSession, db_connection: AsyncConnection
) -> None:
    repository = VisitRepository(db_session)
    visit = await repository.get_one(2)
    assert visit is not None

    visit.status = VisitStatus.COMPLETED
    await repository.session.commit()

    status = await db_connection.scalar(select(Visit.status).where(Visit.id == 2))
    assert status == VisitStatus.COMPLETED


async def test_get_one_leaves_transaction_to_caller(db_session: AsyncSession) -> None:
    await VisitRepository(db_session).get_one(2)

    assert db_session.in_transaction()
