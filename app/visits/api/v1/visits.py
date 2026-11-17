from typing import Annotated

from fastapi import APIRouter, Depends, status
from punq import Container

from app.common.containers.container import init_container
from app.visits.serializers.visits import VisitResponseSchema
from app.visits.services.base import BaseVisitService

router = APIRouter(prefix="/visits", tags=["Visits"])


@router.post(
    "/{id}/complete",
    status_code=status.HTTP_200_OK,
    summary="Complete a visit",
    response_model=VisitResponseSchema,
)
async def complete_visit(
    id: int, container: Annotated[Container, Depends(init_container)]
) -> VisitResponseSchema:
    visit_service: BaseVisitService = container.resolve(BaseVisitService)
    return await visit_service.complete(id)
