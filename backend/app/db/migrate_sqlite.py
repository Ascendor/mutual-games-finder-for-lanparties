from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, func, select, text

from app.core.config import settings
from app.db.session import engine
from app.models import Account, Game, Ownership, Participant, PlatformGameMapping, SyncRun

TABLES = (
    Participant.__table__,
    Game.__table__,
    Account.__table__,
    PlatformGameMapping.__table__,
    Ownership.__table__,
    SyncRun.__table__,
)


def migrate_sqlite_if_needed() -> None:
    path = Path(settings.sqlite_migration_path) if settings.sqlite_migration_path else None
    if engine.dialect.name != "postgresql" or not path or not path.is_file():
        return

    with engine.connect() as target:
        if target.scalar(select(func.count()).select_from(Participant.__table__)):
            print("PostgreSQL already contains data; SQLite migration skipped.")
            return

    source_engine = create_engine(f"sqlite:///{path.as_posix()}")
    copied: dict[str, int] = {}
    try:
        with source_engine.connect() as source, engine.begin() as target:
            for table in TABLES:
                rows = [dict(row) for row in source.execute(select(table)).mappings()]
                if rows:
                    target.execute(table.insert(), rows)
                copied[table.name] = len(rows)

            for table in TABLES:
                target.execute(
                    text(
                        "SELECT setval("
                        "pg_get_serial_sequence(:table_name, 'id'), "
                        f"COALESCE((SELECT MAX(id) FROM {table.name}), 1), "
                        f"(SELECT COUNT(*) > 0 FROM {table.name})"
                        ")"
                    ),
                    {"table_name": table.name},
                )
    finally:
        source_engine.dispose()

    summary = ", ".join(f"{table}={count}" for table, count in copied.items())
    print(f"SQLite migration completed: {summary}")


if __name__ == "__main__":
    migrate_sqlite_if_needed()
