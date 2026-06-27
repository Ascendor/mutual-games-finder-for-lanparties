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
    with op.batch_alter_table("sync_runs") as batch_op:
        batch_op.alter_column("account_id", existing_type=sa.Integer(), nullable=True)
        batch_op.add_column(
            sa.Column("kind", sa.String(length=40), nullable=False, server_default="account")
        )


def downgrade() -> None:
    with op.batch_alter_table("sync_runs") as batch_op:
        batch_op.drop_column("kind")
        batch_op.alter_column("account_id", existing_type=sa.Integer(), nullable=False)
