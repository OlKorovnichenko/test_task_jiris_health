from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.common.database.base import BaseTimestampModel
from app.visits.models.visits import Visit


class VisitOutboxEvent(BaseTimestampModel):
    __tablename__ = "visit_outbox_events"
    __table_args__ = (
        Index(
            "ix_visit_outbox_events_unpublished",
            "created_at",
            "event_id",
            postgresql_where=text("published_at IS NULL"),
        ),
    )

    event_id: Mapped[UUID] = mapped_column(primary_key=True)
    visit_id: Mapped[int] = mapped_column(Integer, ForeignKey(Visit.id), unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claim_token: Mapped[UUID | None] = mapped_column()
    claimed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
