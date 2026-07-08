"""Allow metadata synchronization runs in the shared log.

Revision ID: 0002_metadata_sync_runs
Revises: 0001_initial
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_metadata_sync_runs"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("sync_runs", "account_id", existing_type=sa.Integer(), nullable=True)
    op.add_column("sync_runs", sa.Column("kind", sa.String(length=40), nullable=False, server_default="account"))


def downgrade() -> None:
    op.drop_column("sync_runs", "kind")
    op.alter_column("sync_runs", "account_id", existing_type=sa.Integer(), nullable=False)
