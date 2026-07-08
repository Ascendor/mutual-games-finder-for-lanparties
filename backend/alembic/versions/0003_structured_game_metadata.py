"""Add structured multiplayer metadata and provenance.

Revision ID: 0003_structured_game_metadata
Revises: 0002_metadata_sync_runs
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "0003_structured_game_metadata"
down_revision = "0002_metadata_sync_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("games", sa.Column("campaign_coop", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("games", sa.Column("drop_in", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("games", sa.Column("versus", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("games", sa.Column("offline_max_players", sa.Integer()))
    op.add_column("games", sa.Column("online_max_players", sa.Integer()))
    op.add_column("games", sa.Column("offline_coop_max_players", sa.Integer()))
    op.add_column("games", sa.Column("online_coop_max_players", sa.Integer()))
    op.add_column("games", sa.Column("multiplayer_metadata_known", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("games", sa.Column("player_count_known", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("games", sa.Column("metadata_source", sa.String(length=40)))
    op.add_column("games", sa.Column("metadata_external_id", sa.String(length=120)))
    op.add_column("games", sa.Column("metadata_sources", JSONB(), nullable=False, server_default="{}"))
    op.add_column("games", sa.Column("metadata_updated_at", sa.DateTime()))


def downgrade() -> None:
    for column in (
        "metadata_updated_at",
        "metadata_sources",
        "metadata_external_id",
        "metadata_source",
        "player_count_known",
        "multiplayer_metadata_known",
        "online_coop_max_players",
        "offline_coop_max_players",
        "online_max_players",
        "offline_max_players",
        "versus",
        "drop_in",
        "campaign_coop",
    ):
        op.drop_column("games", column)
