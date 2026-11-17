"""Enforce one billing record per visit regardless of status.

Revision ID: 0005_billing_visit_unique
Revises: 0004_billing_active_record_index
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_billing_visit_unique"
down_revision = "0004_billing_active_record_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("uq_billing_records_active_visit", table_name="billing_records")
    op.create_unique_constraint(
        "billing_records_visit_id_key", "billing_records", ["visit_id"]
    )


def downgrade() -> None:
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
