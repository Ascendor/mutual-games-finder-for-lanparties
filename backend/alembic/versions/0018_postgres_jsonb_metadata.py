"""Use jsonb for structured metadata.

Revision ID: 0018_postgres_jsonb
Revises: 0017_analytics_period
"""

from alembic import op


revision = "0018_postgres_jsonb"
down_revision = "0017_analytics_period"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE games ALTER COLUMN genres TYPE jsonb USING genres::jsonb")
    op.execute("ALTER TABLE games ALTER COLUMN metadata_sources TYPE jsonb USING metadata_sources::jsonb")
    op.execute("ALTER TABLE usage_events ALTER COLUMN details TYPE jsonb USING details::jsonb")
    op.execute("CREATE INDEX ix_games_genres_gin ON games USING gin (genres)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_games_genres_gin")
    op.execute("ALTER TABLE usage_events ALTER COLUMN details TYPE json USING details::json")
    op.execute("ALTER TABLE games ALTER COLUMN metadata_sources TYPE json USING metadata_sources::json")
    op.execute("ALTER TABLE games ALTER COLUMN genres TYPE json USING genres::json")
