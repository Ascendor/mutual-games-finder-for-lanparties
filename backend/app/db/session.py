from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

is_sqlite = settings.database_url.startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {}
engine_options = (
    {}
    if is_sqlite
    else {
        "pool_pre_ping": True,
        "pool_size": 10,
        "max_overflow": 20,
        "pool_recycle": 1800,
    }
)
engine = create_engine(settings.database_url, connect_args=connect_args, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
