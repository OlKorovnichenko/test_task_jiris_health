"""Enforce one active billing record per visit while retaining reversed records.

Revision ID: 0004_billing_active_record_index
Revises: 0003_create_billing_tables
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_billing_active_record_index"
down_revision = "0003_create_billing_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "billing_records_visit_id_key", "billing_records", type_="unique"
    )
    op.create_index(
        "uq_billing_records_active_visit",
        "billing_records",
        ["visit_id"],
        unique=True,
        postgresql_where=sa.text("status = 'Created'"),
    )


def downgrade() -> None:
    op.drop_index("uq_billing_records_active_visit", table_name="billing_records")
    op.create_unique_constraint(
        "billing_records_visit_id_key", "billing_records", ["visit_id"]
    )
