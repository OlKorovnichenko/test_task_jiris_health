from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.common.database.base import BaseTimestampModel
from app.visits.models.visits import Visit


class VisitOutboxEvent(BaseTimestampModel):
    __tablename__ = "visit_outbox_events"

    event_id: Mapped[UUID] = mapped_column(primary_key=True)
    visit_id: Mapped[int] = mapped_column(Integer, ForeignKey(Visit.id), unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
