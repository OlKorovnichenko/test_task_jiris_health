"""create billing tables

Revision ID: 0003_create_billing_tables
Revises: 0002_create_visit_outbox
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_create_billing_tables"
down_revision = "0002_create_visit_outbox"
branch_labels = None
depends_on = None


billing_status = postgresql.ENUM(
    "Created", "Reversed", name="billing_status", create_type=False
)


def upgrade() -> None:
    billing_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "billing_processed_events",
        sa.Column("event_id", sa.Uuid(), nullable=False),
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
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_table(
        "billing_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("visit_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=20, scale=2), nullable=False),
        sa.Column(
            "status",
            billing_status,
            server_default="Created",
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
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "amount >= 0", name="ck_billing_records_non_negative_amount"
        ),
    )
    op.create_index("ix_billing_records_visit_id", "billing_records", ["visit_id"])
    op.create_index(
        "uq_billing_records_active_visit",
        "billing_records",
        ["visit_id"],
        unique=True,
        postgresql_where=sa.text("status = 'Created'"),
    )


def downgrade() -> None:
    op.drop_table("billing_records")
    op.drop_table("billing_processed_events")
    billing_status.drop(op.get_bind(), checkfirst=True)
