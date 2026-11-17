from abc import ABC, abstractmethod

from app.visits.serializers.visits import VisitResponseSchema


class BaseVisitService(ABC):
    @abstractmethod
    async def complete(self, visit_id: int) -> VisitResponseSchema: ...
