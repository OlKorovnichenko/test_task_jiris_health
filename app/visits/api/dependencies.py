from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.database.session import get_session
from app.visits.repositories.visits import VisitRepository
from app.visits.services.base import BaseVisitService
from app.visits.services.visits import VisitService


def get_visit_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BaseVisitService:
    return VisitService(VisitRepository(session))
