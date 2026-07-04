"""Add persistent analytics party period.

Revision ID: 0017_analytics_period
Revises: 0016_usage_analytics
"""

from alembic import op
import sqlalchemy as sa


revision = "0017_analytics_period"
down_revision = "0016_usage_analytics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analytics_configuration",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("party_start_at", sa.DateTime()),
        sa.Column("party_end_at", sa.DateTime()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("analytics_configuration")
