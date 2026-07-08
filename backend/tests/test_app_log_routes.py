from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.db.base import Base
from app.db.session import get_db
from app.main import app


def test_app_log_entry_endpoint_replaces_old_public_paths():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    db = Session()
    participant = models.Participant(nickname="PlayerTwo")
    db.add(participant)
    db.commit()
    client = TestClient(app)

    try:
        response = client.post(
            "/api/app-log/entries",
            json={
                "participant_id": participant.id,
                "event_type": "page_view",
                "details": {"path": "/"},
            },
        )

        assert response.status_code == 201
        assert response.json()["participant_name"] == "PlayerTwo"
        assert client.post("/api/app-log/events", json={}).status_code == 404
        assert client.post("/api/analytics/entries", json={}).status_code == 404
        assert client.post("/api/analytics/events", json={}).status_code == 404
    finally:
        app.dependency_overrides.clear()
