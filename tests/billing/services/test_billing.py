from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.billing.services.billing import BillingService
from app.common.events import VisitCompleted


@pytest.mark.parametrize(
    ("duration", "rate", "expected"),
    [
        (timedelta(minutes=90), "200.00", "300.00"),
        (timedelta(minutes=1), "1.50", "0.03"),
        (timedelta(microseconds=1), "200.00", "0.00"),
        (timedelta(days=2, minutes=30), "10.00", "485.00"),
        (timedelta(hours=1), "0.00", "0.00"),
    ],
)
def test_calculate_amount(duration: timedelta, rate: str, expected: str) -> None:
    start = datetime(2026, 11, 16, 9, tzinfo=UTC)
    event = VisitCompleted(
        visit_id=2,
        start_date_time=start,
        end_date_time=start + duration,
        rate=Decimal(rate),
    )

    assert BillingService._calculate_amount(event) == Decimal(expected)


def test_duration_uses_elapsed_time_across_daylight_saving() -> None:
    zone = ZoneInfo("Europe/Kyiv")
    event = VisitCompleted(
        visit_id=2,
        start_date_time=datetime(2026, 10, 25, 2, tzinfo=zone),
        end_date_time=datetime(2026, 10, 25, 4, tzinfo=zone),
        rate=Decimal("100.00"),
    )

    assert BillingService._calculate_amount(event) == Decimal("300.00")


@pytest.mark.parametrize(
    "changes",
    [
        {"rate": "-1.00"},
        {"rate": "1.001"},
        {"end_date_time": "2026-11-16T09:00:00Z"},
        {"start_date_time": "2026-11-16T09:00:00"},
        {"event_name": "UnknownEvent"},
    ],
)
def test_invalid_events_are_rejected(changes: dict[str, object]) -> None:
    payload = {
        "visit_id": 2,
        "start_date_time": "2026-11-16T09:00:00Z",
        "end_date_time": "2026-11-16T10:30:00Z",
        "rate": "200.00",
        **changes,
    }
    with pytest.raises(ValidationError):
        VisitCompleted.model_validate(payload)
