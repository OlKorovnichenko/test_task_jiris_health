import logging

from app.common.events import VisitCompleted
from app.visits.exceptions import (
    InvalidVisitStatusError,
    VisitCompletionError,
    VisitNotFoundError,
)
from app.visits.repositories.base import BaseVisitRepository
from app.visits.serializers.visits import VisitResponseSchema
from app.visits.services.base import BaseVisitService
from app.visits.utils.enumerations.visit_enums import VisitStatus

logger = logging.getLogger(__name__)


class VisitService(BaseVisitService):
    def __init__(self, repository: BaseVisitRepository) -> None:
        self._repository = repository

    async def complete(self, visit_id: int) -> VisitResponseSchema:
        try:
            async with self._repository.transaction():
                return await self._complete(visit_id)
        except VisitNotFoundError, InvalidVisitStatusError:
            raise
        except Exception as exc:
            logger.exception(f"Failed to complete visit {visit_id}")
            raise VisitCompletionError("Failed to complete visit") from exc

    async def _complete(self, visit_id: int) -> VisitResponseSchema:
        visit = await self._repository.get_for_update(visit_id)
        if visit is None:
            raise VisitNotFoundError()

        if visit.status != VisitStatus.IN_PROGRESS:
            raise InvalidVisitStatusError(visit.status)

        visit.status = VisitStatus.COMPLETED
        self._repository.add_completed_event(
            VisitCompleted(
                visit_id=visit.id,
                start_date_time=visit.start_date_time,
                end_date_time=visit.end_date_time,
                rate=visit.rate,
            )
        )
        return VisitResponseSchema(id=visit.id, status=visit.status)
