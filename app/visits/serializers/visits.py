from pydantic import BaseModel

from app.visits.utils.enumerations.visit_enums import VisitStatus


class VisitResponseSchema(BaseModel):
    id: int
    status: VisitStatus
