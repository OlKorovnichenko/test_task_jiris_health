from decimal import Decimal
from uuid import UUID

from sqlalchemy import Enum, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.billing.utils.enumerations.billing_enums import BillingStatus
from app.common.database.base import BaseTimestampModel


class BillingRecord(BaseTimestampModel):
    __tablename__ = "billing_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    visit_id: Mapped[int] = mapped_column(Integer, unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    status: Mapped[BillingStatus] = mapped_column(
        Enum(
            BillingStatus,
            name="billing_status",
            values_callable=lambda items: [item.value for item in items],
            validate_strings=True,
        ),
        default=BillingStatus.CREATED,
        server_default=BillingStatus.CREATED.value,
    )


class ProcessedBillingEvent(BaseTimestampModel):
    __tablename__ = "billing_processed_events"

    event_id: Mapped[UUID] = mapped_column(primary_key=True)
