from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from unittest.mock import MagicMock, create_autospec

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.visits.exceptions import (
    InvalidVisitStatusError,
    VisitCompletionError,
    VisitNotFoundError,
)
from app.visits.models.visits import Visit
from app.visits.repositories.base import BaseVisitRepository
from app.visits.services.visits import VisitService
from app.visits.utils.enumerations.visit_enums import VisitStatus


@pytest.fixture
def repository() -> MagicMock:
    repository = create_autospec(BaseVisitRepository, instance=True)
    repository.transaction.return_value.__aexit__.return_value = False
    return repository


def in_progress_visit() -> Visit:
    return Visit(
        id=10,
        status=VisitStatus.IN_PROGRESS,
        start_date_time=datetime(2026, 11, 16, 9, tzinfo=UTC),
        end_date_time=datetime(2026, 11, 16, 10, 30, tzinfo=UTC),
        rate=Decimal("200.00"),
    )


async def test_completes_visit_and_event_in_one_transaction(
    repository: MagicMock,
) -> None:
    visit = in_progress_visit()
    repository.get_for_update.return_value = visit
    service = VisitService(cast(BaseVisitRepository, repository))

    result = await service.complete(10)

    assert result.id == 10
    assert result.status == VisitStatus.COMPLETED
    assert visit.status == VisitStatus.COMPLETED
    repository.get_for_update.assert_awaited_once_with(10)
    event = repository.add_completed_event.call_args.args[0]
    assert event.visit_id == visit.id
    assert event.rate == visit.rate
    assert event.start_date_time == visit.start_date_time
    assert event.end_date_time == visit.end_date_time
    repository.transaction.return_value.__aexit__.assert_awaited_once_with(
        None, None, None
    )


@pytest.mark.parametrize(
    "status",
    [
        VisitStatus.SCHEDULED,
        VisitStatus.COMPLETED,
        VisitStatus.CANCELED,
        VisitStatus.MISSED,
    ],
)
async def test_invalid_status_is_not_changed(
    repository: MagicMock, status: VisitStatus
) -> None:
    visit = Visit(id=10, status=status)
    repository.get_for_update.return_value = visit
    service = VisitService(cast(BaseVisitRepository, repository))

    with pytest.raises(InvalidVisitStatusError) as error:
        await service.complete(10)

    assert error.value.status == status
    assert visit.status == status
    repository.add_completed_event.assert_not_called()
    assert (
        repository.transaction.return_value.__aexit__.call_args.args[0]
        is InvalidVisitStatusError
    )


async def test_missing_visit(repository: MagicMock) -> None:
    repository.get_for_update.return_value = None
    service = VisitService(cast(BaseVisitRepository, repository))

    with pytest.raises(VisitNotFoundError, match="Visit not found"):
        await service.complete(10)

    repository.add_completed_event.assert_not_called()


async def test_commit_failure_logs_traceback_and_raises_domain_error(
    repository: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    repository.get_for_update.return_value = in_progress_visit()
    repository.transaction.return_value.__aexit__.side_effect = SQLAlchemyError(
        "Commit failed"
    )
    service = VisitService(cast(BaseVisitRepository, repository))

    with pytest.raises(VisitCompletionError, match="Failed to complete visit") as error:
        await service.complete(10)

    assert isinstance(error.value.__cause__, SQLAlchemyError)
    assert "Failed to complete visit 10" in caplog.text
    assert any(record.exc_info for record in caplog.records)
