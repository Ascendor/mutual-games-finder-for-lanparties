"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "participants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nickname", sa.String(120), nullable=False, unique=True),
        sa.Column("real_name", sa.String(180)),
        sa.Column("present", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "games",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("normalized_title", sa.String(255), nullable=False, index=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("cover_url", sa.String(800)),
        sa.Column("release_date", sa.Date()),
        sa.Column("genres", JSONB(), nullable=False, server_default="[]"),
        sa.Column("singleplayer", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("multiplayer", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("lan", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("local_coop", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("online_coop", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("hotseat", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("split_screen", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("shared_screen", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("min_players", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_players", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("participant_id", sa.Integer(), sa.ForeignKey("participants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform", sa.String(40), nullable=False),
        sa.Column("account_id", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("last_successful_sync", sa.DateTime()),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("platform", "account_id", name="uq_account_platform_id"),
    )
    op.create_table(
        "platform_game_mappings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("game_id", sa.Integer(), sa.ForeignKey("games.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform", sa.String(40), nullable=False),
        sa.Column("platform_game_id", sa.String(255), nullable=False),
        sa.Column("platform_title", sa.String(255), nullable=False),
        sa.Column("normalized_title", sa.String(255), nullable=False, index=True),
        sa.UniqueConstraint("platform", "platform_game_id", name="uq_platform_game"),
    )
    op.create_table(
        "ownerships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("participant_id", sa.Integer(), sa.ForeignKey("participants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("game_id", sa.Integer(), sa.ForeignKey("games.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform", sa.String(40), nullable=False),
        sa.Column("playtime_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("owned_since", sa.DateTime()),
        sa.Column("last_seen", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("participant_id", "game_id", "platform", name="uq_owner_game_platform"),
    )
    op.create_table(
        "sync_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime()),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("imported_games", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("sync_runs")
    op.drop_table("ownerships")
    op.drop_table("platform_game_mappings")
    op.drop_table("accounts")
    op.drop_table("games")
    op.drop_table("participants")
