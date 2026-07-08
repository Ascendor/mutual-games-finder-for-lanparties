"""Add indexes for list and recommendation queries.

Revision ID: 0004_postgresql_indexes
Revises: 0003_structured_game_metadata
"""

from alembic import op


revision = "0004_postgresql_indexes"
down_revision = "0003_structured_game_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_games_title", "games", ["title"])
    op.create_index("ix_ownerships_participant_id", "ownerships", ["participant_id"])
    op.create_index("ix_ownerships_game_id", "ownerships", ["game_id"])
    op.create_index("ix_ownerships_account_id", "ownerships", ["account_id"])
    op.create_index("ix_ownerships_participant_game", "ownerships", ["participant_id", "game_id"])
    op.create_index("ix_accounts_participant_id", "accounts", ["participant_id"])
    op.create_index("ix_platform_game_mappings_game_id", "platform_game_mappings", ["game_id"])
    op.create_index("ix_sync_runs_started_at", "sync_runs", ["started_at"])

    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE INDEX ix_games_normalized_title_trgm ON games USING gin (normalized_title gin_trgm_ops)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_games_normalized_title_trgm")
    op.drop_index("ix_sync_runs_started_at", table_name="sync_runs")
    op.drop_index("ix_platform_game_mappings_game_id", table_name="platform_game_mappings")
    op.drop_index("ix_accounts_participant_id", table_name="accounts")
    op.drop_index("ix_ownerships_participant_game", table_name="ownerships")
    op.drop_index("ix_ownerships_account_id", table_name="ownerships")
    op.drop_index("ix_ownerships_game_id", table_name="ownerships")
    op.drop_index("ix_ownerships_participant_id", table_name="ownerships")
    op.drop_index("ix_games_title", table_name="games")
