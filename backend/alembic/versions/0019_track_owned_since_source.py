"""Track acquisition sources and first-seen dates.

Revision ID: 0019_owned_since_source
Revises: 0018_postgres_jsonb
"""

import sqlalchemy as sa
from alembic import op


revision = "0019_owned_since_source"
down_revision = "0018_postgres_jsonb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ownerships", sa.Column("owned_since_source", sa.String(length=40), nullable=True))
    op.add_column("ownerships", sa.Column("first_seen_at", sa.DateTime(), nullable=True))
    op.add_column(
        "ownerships",
        sa.Column(
            "first_seen_is_baseline",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.alter_column("ownerships", "first_seen_is_baseline", server_default=sa.false())


def downgrade() -> None:
    op.drop_column("ownerships", "first_seen_is_baseline")
    op.drop_column("ownerships", "first_seen_at")
    op.drop_column("ownerships", "owned_since_source")
