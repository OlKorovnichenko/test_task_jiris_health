from typing import cast
from unittest.mock import MagicMock, create_autospec

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.visits.models.visits import Visit
from app.visits.repositories.base import BaseVisitRepository
from app.visits.services.visits import VisitService
from app.visits.utils.enumerations.visit_enums import VisitStatus


@pytest.fixture
def repository() -> MagicMock:
    repository = create_autospec(BaseVisitRepository, instance=True)
    repository.session = create_autospec(AsyncSession, instance=True)
    return repository


async def test_completes_and_commits_visit(repository: MagicMock) -> None:
    visit = Visit(id=10, status=VisitStatus.IN_PROGRESS)
    repository.get_one.return_value = visit
    service = VisitService(cast(BaseVisitRepository, repository))

    result = await service.complete(10)

    assert result.id == 10
    assert result.status == VisitStatus.COMPLETED
    assert visit.status == VisitStatus.COMPLETED
    repository.get_one.assert_awaited_once_with(10)
    repository.session.commit.assert_awaited_once_with()


@pytest.mark.parametrize(
    "status",
    [
        VisitStatus.SCHEDULED,
        VisitStatus.COMPLETED,
        VisitStatus.CANCELED,
        VisitStatus.MISSED,
    ],
)
async def test_invalid_status_is_not_changed_or_committed(
    repository: MagicMock, status: VisitStatus
) -> None:
    visit = Visit(id=10, status=status)
    repository.get_one.return_value = visit
    service = VisitService(cast(BaseVisitRepository, repository))

    with pytest.raises(HTTPException) as error:
        await service.complete(10)

    assert error.value.status_code == 400
    assert visit.status == status
    repository.session.commit.assert_not_awaited()


async def test_missing_visit_is_not_committed(repository: MagicMock) -> None:
    repository.get_one.return_value = None
    service = VisitService(cast(BaseVisitRepository, repository))

    with pytest.raises(HTTPException) as error:
        await service.complete(10)

    assert error.value.status_code == 404
    repository.session.commit.assert_not_awaited()


async def test_commit_failure_propagates(repository: MagicMock) -> None:
    repository.get_one.return_value = Visit(id=10, status=VisitStatus.IN_PROGRESS)
    repository.session.commit.side_effect = SQLAlchemyError("Commit failed")
    service = VisitService(cast(BaseVisitRepository, repository))

    with pytest.raises(SQLAlchemyError, match="Commit failed"):
        await service.complete(10)
