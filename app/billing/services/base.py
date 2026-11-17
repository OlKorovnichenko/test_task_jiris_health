from abc import ABC, abstractmethod

from app.common.events import VisitCompleted


class BaseBillingService(ABC):
    @abstractmethod
    async def process_visit_completed(self, event: VisitCompleted) -> None: ...
