"""share recommendation cache revisions

Revision ID: 0008_cache_revision
Revises: 0007_free_games
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_cache_revision"
down_revision = "0007_free_games"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table = op.create_table(
        "recommendation_cache_revisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.bulk_insert(table, [{"id": 1, "revision": 0}])


def downgrade() -> None:
    op.drop_table("recommendation_cache_revisions")
