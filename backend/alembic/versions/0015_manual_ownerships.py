"""Add durable manual ownership confirmations.

Revision ID: 0015_manual_ownerships
Revises: 0014_soft_non_games
"""

from alembic import op
import sqlalchemy as sa


revision = "0015_manual_ownerships"
down_revision = "0014_soft_non_games"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ownerships") as batch_op:
        batch_op.alter_column(
            "account_id",
            existing_type=sa.Integer(),
            nullable=True,
        )

    op.create_table(
        "manual_ownerships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "participant_id",
            sa.Integer(),
            sa.ForeignKey("participants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "game_id",
            sa.Integer(),
            sa.ForeignKey("games.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("platform", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "participant_id",
            "game_id",
            "platform",
            name="uq_manual_owner_game_platform",
        ),
    )
    op.create_index(
        "ix_manual_ownerships_participant_id",
        "manual_ownerships",
        ["participant_id"],
    )
    op.create_index(
        "ix_manual_ownerships_game_id",
        "manual_ownerships",
        ["game_id"],
    )


def downgrade() -> None:
    op.execute("DELETE FROM ownerships WHERE account_id IS NULL")
    op.drop_index("ix_manual_ownerships_game_id", table_name="manual_ownerships")
    op.drop_index("ix_manual_ownerships_participant_id", table_name="manual_ownerships")
    op.drop_table("manual_ownerships")
    with op.batch_alter_table("ownerships") as batch_op:
        batch_op.alter_column(
            "account_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
