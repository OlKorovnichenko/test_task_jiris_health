from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, Enum, Integer, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.database.base import BaseTimestampModel
from app.visits.utils.enumerations.visit_enums import VisitStatus


class Visit(BaseTimestampModel):
    __tablename__ = "visits"
    __table_args__ = (
        CheckConstraint(
            "end_date_time > start_date_time", name="ck_visits_positive_duration"
        ),
        CheckConstraint("rate >= 0", name="ck_visits_non_negative_rate"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    start_date_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_date_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    description: Mapped[str] = mapped_column(Text)
    rate: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    status: Mapped[VisitStatus] = mapped_column(
        Enum(
            VisitStatus,
            name="visit_status",
            values_callable=lambda items: [item.value for item in items],
            validate_strings=True,
        ),
        default=VisitStatus.SCHEDULED,
        server_default=VisitStatus.SCHEDULED.value,
    )
