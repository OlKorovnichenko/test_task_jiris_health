"""Create visits and its status enum."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_create_visits"
down_revision = None
branch_labels = None
depends_on = None

visit_status = postgresql.ENUM(
    "Scheduled",
    "In Progress",
    "Completed",
    "Canceled",
    "Missed",
    name="visit_status",
    create_type=False,
)


def upgrade() -> None:
    visit_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "visits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("start_date_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_date_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("rate", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "status",
            visit_status,
            server_default=sa.text("'Scheduled'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "end_date_time > start_date_time", name="ck_visits_positive_duration"
        ),
        sa.CheckConstraint("rate >= 0", name="ck_visits_non_negative_rate"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("visits")
    visit_status.drop(op.get_bind(), checkfirst=True)
