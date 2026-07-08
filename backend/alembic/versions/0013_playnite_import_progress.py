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
    op.add_column("sync_runs", sa.Column("participant_id", sa.Integer()))
    op.add_column("sync_runs", sa.Column("stage", sa.String(length=40), nullable=False, server_default=""))
    op.add_column("sync_runs", sa.Column("progress_current", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("sync_runs", sa.Column("progress_total", sa.Integer(), nullable=False, server_default="0"))
    op.create_foreign_key(
        "fk_sync_runs_participant_id",
        "sync_runs",
        "participants",
        ["participant_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_sync_runs_participant_id", "sync_runs", type_="foreignkey")
    op.drop_column("sync_runs", "progress_total")
    op.drop_column("sync_runs", "progress_current")
    op.drop_column("sync_runs", "stage")
    op.drop_column("sync_runs", "participant_id")
