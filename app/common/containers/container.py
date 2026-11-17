from typing import Annotated

from fastapi import Depends
from punq import Container
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.repositories.base import BaseBillingRepository
from app.billing.repositories.billing import BillingRepository
from app.billing.services.base import BaseBillingService
from app.billing.services.billing import BillingService
from app.common.database.session import get_session
from app.visits.repositories.base import BaseVisitRepository
from app.visits.repositories.visits import VisitRepository
from app.visits.services.base import BaseVisitService
from app.visits.services.visits import VisitService


def init_container(session: Annotated[AsyncSession, Depends(get_session)]) -> Container:
    container = Container()
    container.register(AsyncSession, instance=session)
    container.register(BaseVisitRepository, VisitRepository)
    container.register(BaseVisitService, VisitService)
    container.register(BaseBillingRepository, BillingRepository)
    container.register(BaseBillingService, BillingService)
    return container
