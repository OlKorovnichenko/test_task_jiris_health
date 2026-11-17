from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.visits.api.dependencies import get_visit_service
from app.visits.exceptions import (
    InvalidVisitStatusError,
    VisitCompletionError,
    VisitNotFoundError,
)
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
    id: Annotated[int, Path(gt=0)],
    visit_service: Annotated[BaseVisitService, Depends(get_visit_service)],
) -> VisitResponseSchema:
    try:
        return await visit_service.complete(id)
    except VisitNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidVisitStatusError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except VisitCompletionError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
