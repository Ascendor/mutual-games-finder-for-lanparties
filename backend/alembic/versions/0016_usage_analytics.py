"""Add local usage analytics events.

Revision ID: 0016_usage_analytics
Revises: 0015_manual_ownerships
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "0016_usage_analytics"
down_revision = "0015_manual_ownerships"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usage_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "participant_id",
            sa.Integer(),
            sa.ForeignKey("participants.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "participant_name",
            sa.String(length=120),
            nullable=False,
            server_default="",
        ),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "details",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.create_index("ix_usage_events_participant_id", "usage_events", ["participant_id"])
    op.create_index("ix_usage_events_event_type", "usage_events", ["event_type"])
    op.create_index("ix_usage_events_occurred_at", "usage_events", ["occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_usage_events_occurred_at", table_name="usage_events")
    op.drop_index("ix_usage_events_event_type", table_name="usage_events")
    op.drop_index("ix_usage_events_participant_id", table_name="usage_events")
    op.drop_table("usage_events")
