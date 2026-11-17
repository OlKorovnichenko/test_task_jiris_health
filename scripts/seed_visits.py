"""Add demo visits explicitly; never run during migrations."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.common.database.session import dispose_database, get_database
from app.visits.models.visits import Visit
from app.visits.utils.enumerations.visit_enums import VisitStatus


async def seed() -> None:
    now = datetime.now(UTC)
    try:
        async with get_database().sessions.begin() as session:
            session.add_all(
                [
                    Visit(
                        start_date_time=now,
                        end_date_time=now + timedelta(minutes=90),
                        description=f"Demo visit: {status.value}",
                        rate=Decimal("200.00"),
                        status=status,
                    )
                    for status in (VisitStatus.SCHEDULED, VisitStatus.IN_PROGRESS)
                ]
            )
    finally:
        await dispose_database()


if __name__ == "__main__":
    asyncio.run(seed())
