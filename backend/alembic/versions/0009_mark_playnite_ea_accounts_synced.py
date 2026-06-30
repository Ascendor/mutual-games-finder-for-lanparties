"""mark existing Playnite EA accounts as synced

Revision ID: 0009_playnite_ea
Revises: 0008_cache_revision
"""

from alembic import op


revision = "0009_playnite_ea"
down_revision = "0008_cache_revision"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE accounts AS account
        SET last_successful_sync = imported.last_seen,
            last_error = NULL
        FROM (
            SELECT account_id, max(last_seen) AS last_seen
            FROM ownerships
            WHERE platform = 'ea'
            GROUP BY account_id
        ) AS imported
        WHERE account.id = imported.account_id
          AND account.platform = 'ea'
          AND account.last_successful_sync IS NULL
        """
    )


def downgrade() -> None:
    pass
