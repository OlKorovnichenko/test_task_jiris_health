import logging

from fastapi import HTTPException

from app.common.events import VisitCompleted
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
            return await self._complete(visit_id)
        except HTTPException:
            await self._repository.session.rollback()
            raise
        except Exception as exc:
            await self._repository.session.rollback()
            raise HTTPException(
                status_code=500, detail="Failed to complete visit"
            ) from exc

    async def _complete(self, visit_id: int) -> VisitResponseSchema:
        visit = await self._repository.get_one(visit_id)
        if visit is None:
            raise HTTPException(status_code=404, detail="Visit not found")

        if visit.status == VisitStatus.COMPLETED:
            raise HTTPException(status_code=400, detail="Visit already completed")

        if visit.status == VisitStatus.CANCELED:
            raise HTTPException(status_code=400, detail="Visit already cancelled")

        if visit.status == VisitStatus.SCHEDULED:
            raise HTTPException(status_code=400, detail="Visit not started yet")

        if visit.status == VisitStatus.MISSED:
            raise HTTPException(status_code=400, detail="Visit already missed")

        visit.status = VisitStatus.COMPLETED
        self._repository.add_completed_event(
            VisitCompleted(
                visit_id=visit.id,
                start_date_time=visit.start_date_time,
                end_date_time=visit.end_date_time,
                rate=visit.rate,
            )
        )
        await self._repository.session.commit()
        return VisitResponseSchema(id=visit.id, status=visit.status)
