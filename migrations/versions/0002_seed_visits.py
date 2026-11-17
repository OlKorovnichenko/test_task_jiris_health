"""Add test visits covering every visit status."""

from datetime import UTC, datetime
from decimal import Decimal

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_seed_visits"
down_revision = "0001_create_visits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    visits = sa.table(
        "visits",
        sa.column("id", sa.Integer()),
        sa.column("start_date_time", sa.DateTime(timezone=True)),
        sa.column("end_date_time", sa.DateTime(timezone=True)),
        sa.column("description", sa.Text()),
        sa.column("rate", sa.Numeric(10, 2)),
        sa.column(
            "status",
            postgresql.ENUM(
                "Scheduled",
                "In Progress",
                "Completed",
                "Canceled",
                "Missed",
                name="visit_status",
                create_type=False,
            ),
        ),
    )
    op.bulk_insert(
        visits,
        [
            {
                "id": visit_id,
                "start_date_time": datetime(2026, 11, day, 9, tzinfo=UTC),
                "end_date_time": datetime(2026, 11, day, 10, 30, tzinfo=UTC),
                "description": f"Test visit: {status}",
                "rate": Decimal("200.00"),
                "status": status,
            }
            for visit_id, day, status in (
                (1, 17, "Scheduled"),
                (2, 16, "In Progress"),
                (3, 15, "Completed"),
                (4, 14, "Canceled"),
                (5, 13, "Missed"),
            )
        ],
    )
    op.execute(
        "SELECT setval(pg_get_serial_sequence('visits', 'id'), "
        "(SELECT MAX(id) FROM visits))"
    )


def downgrade() -> None:
    op.execute("DELETE FROM visits WHERE id IN (1, 2, 3, 4, 5)")
