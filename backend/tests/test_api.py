from fastapi.testclient import TestClient
import json
import zipfile
from io import BytesIO

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app import models  # noqa: F401
from app.api.imports import UPLOAD_CHUNK_SIZE
from app.core.config import settings


def test_participant_api_roundtrip():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    response = client.post("/api/participants", json={"nickname": "Mira", "present": True})
    assert response.status_code == 201
    assert response.json()["nickname"] == "Mira"
    assert client.get("/api/participants").json()[0]["nickname"] == "Mira"
    app.dependency_overrides.clear()


def test_game_options_are_compact_searchable_and_cacheable():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
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
    db.add_all(
        [
            models.Game(title="Portal", normalized_title="portal"),
            models.Game(title="Portal 2", normalized_title="portal 2"),
            models.Game(title="Quake", normalized_title="quake"),
        ]
    )
    db.commit()
    client = TestClient(app)

    response = client.get("/api/games/options?search=portal")
    assert response.status_code == 200
    assert [item["title"] for item in response.json()] == ["Portal", "Portal 2"]
    assert set(response.json()[0]) == {"id", "title"}
    assert response.headers["cache-control"].startswith("private, max-age=300")

    cached = client.get("/api/games/options", headers={"If-None-Match": response.headers["etag"]})
    assert cached.status_code == 304
    app.dependency_overrides.clear()




def test_game_owners_endpoint_returns_present_deduplicated_owners():
    from datetime import datetime

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
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
    try:
        ada = models.Participant(nickname="Ada", present=True)
        bob = models.Participant(nickname="Bob", present=False)
        game = models.Game(title="Quake III Arena", normalized_title="quake iii arena", multiplayer=True)
        db.add_all([ada, bob, game])
        db.flush()
        ada_steam = models.Account(participant_id=ada.id, platform=models.Platform.steam, account_id="ada-steam", display_name="AdaSteam")
        ada_gog = models.Account(participant_id=ada.id, platform=models.Platform.gog, account_id="ada-gog", display_name="AdaGOG")
        bob_steam = models.Account(participant_id=bob.id, platform=models.Platform.steam, account_id="bob-steam", display_name="BobSteam")
        db.add_all([ada_steam, ada_gog, bob_steam])
        db.flush()
        db.add_all([
            models.Ownership(participant_id=ada.id, account_id=ada_steam.id, game_id=game.id, platform=models.Platform.steam, playtime_minutes=120, last_seen=datetime.utcnow()),
            models.Ownership(participant_id=ada.id, account_id=ada_gog.id, game_id=game.id, platform=models.Platform.gog, playtime_minutes=30, last_seen=datetime.utcnow()),
            models.Ownership(participant_id=bob.id, account_id=bob_steam.id, game_id=game.id, platform=models.Platform.steam, playtime_minutes=999, last_seen=datetime.utcnow()),
        ])
        db.commit()
        client = TestClient(app)
        response = client.get(f"/api/games/{game.id}/owners")
        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 1
        assert payload[0]["participant"]["nickname"] == "Ada"
        assert payload[0]["platforms"] == ["gog", "steam"]
        assert payload[0]["total_playtime_minutes"] == 150

        all_response = client.get(f"/api/games/{game.id}/owners?present_only=false")
        assert [item["participant"]["nickname"] for item in all_response.json()] == ["Bob", "Ada"]
    finally:
        db.close()
        app.dependency_overrides.clear()


def test_account_create_reuses_participant_platform():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    participant = client.post("/api/participants", json={"nickname": "Lob", "present": True}).json()
    first = client.post("/api/accounts", json={"participant_id": participant["id"], "platform": "ubisoft"})
    second = client.post("/api/accounts", json={"participant_id": participant["id"], "platform": "ubisoft"})

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    assert len(client.get("/api/accounts").json()) == 1
    app.dependency_overrides.clear()


def test_playnite_upload_streams_to_disk_and_removes_temp_file(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(settings, "playnite_upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "playnite_upload_max_bytes", 16 * 1024 * 1024)
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    participant = client.post("/api/participants", json={"nickname": "Stream", "present": True}).json()
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("unused-large-member.bin", b"x" * (UPLOAD_CHUNK_SIZE + 1024))
        archive.writestr(
            "library/games.json",
            json.dumps({"Games": [{"Name": "FTL", "Source": {"Name": "GOG"}, "ProductId": "ftl-gog"}]}),
        )

    response = client.post(
        "/api/imports/playnite",
        data={"participant_id": str(participant["id"])},
        files={"file": ("playnite.zip", buffer.getvalue(), "application/zip")},
    )

    assert response.status_code == 200
    assert response.json()["imported_games"] == 1
    assert list(tmp_path.iterdir()) == []
    app.dependency_overrides.clear()


def test_playnite_upload_rejects_oversized_file_and_removes_temp_file(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(settings, "playnite_upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "playnite_upload_max_bytes", 32)
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)

    response = client.post(
        "/api/imports/playnite",
        data={"participant_id": "1"},
        files={"file": ("too-large.zip", b"x" * 64, "application/zip")},
    )

    assert response.status_code == 413
    assert list(tmp_path.iterdir()) == []
    app.dependency_overrides.clear()
