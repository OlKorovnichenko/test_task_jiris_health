"""Create the Visits transactional outbox and pending-event index."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_create_visit_outbox"
down_revision = "0001_create_visits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "visit_outbox_events",
        sa.Column("event_id", sa.Uuid(), primary_key=True),
        sa.Column("visit_id", sa.Integer(), sa.ForeignKey("visits.id"), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claim_token", sa.Uuid(), nullable=True),
        sa.Column("claimed_until", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("visit_id"),
    )
    op.create_index(
        "ix_visit_outbox_events_unpublished",
        "visit_outbox_events",
        ["created_at", "event_id"],
        postgresql_where=sa.text("published_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("visit_outbox_events")
