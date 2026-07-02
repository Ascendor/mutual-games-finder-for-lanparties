"""Add persistent progress fields for Playnite import jobs.

Revision ID: 0013_playnite_progress
Revises: 0012_gog_title_tokens
"""

from alembic import op
import sqlalchemy as sa


revision = "0013_playnite_progress"
down_revision = "0012_gog_title_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("sync_runs") as batch_op:
        batch_op.add_column(sa.Column("participant_id", sa.Integer()))
        batch_op.add_column(
            sa.Column("stage", sa.String(length=40), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column("progress_current", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("progress_total", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.create_foreign_key(
            "fk_sync_runs_participant_id",
            "participants",
            ["participant_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("sync_runs") as batch_op:
        batch_op.drop_constraint("fk_sync_runs_participant_id", type_="foreignkey")
        batch_op.drop_column("progress_total")
        batch_op.drop_column("progress_current")
        batch_op.drop_column("stage")
        batch_op.drop_column("participant_id")
