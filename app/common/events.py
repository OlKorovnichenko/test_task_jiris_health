from datetime import UTC
from decimal import Decimal
from typing import Literal, Self
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, Field, model_validator


class VisitCompleted(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    event_name: Literal["VisitCompleted"] = "VisitCompleted"
    visit_id: int = Field(gt=0)
    start_date_time: AwareDatetime
    end_date_time: AwareDatetime
    rate: Decimal = Field(ge=0, max_digits=10, decimal_places=2)

    @model_validator(mode="after")
    def validate_duration(self) -> Self:
        if self.end_date_time.astimezone(UTC) <= self.start_date_time.astimezone(UTC):
            raise ValueError("Visit duration must be positive")
        return self
