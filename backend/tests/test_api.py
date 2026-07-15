import json
import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path

from app import models  # noqa: F401
from app.api import imports as imports_api
from app.api.imports import UPLOAD_CHUNK_SIZE
from app.core.config import settings


def test_participant_api_roundtrip(client):
    response = client.post("/api/participants", json={"nickname": "Mira", "present": True})
    assert response.status_code == 201
    assert response.json()["nickname"] == "Mira"
    assert client.get("/api/participants").json()[0]["nickname"] == "Mira"


def test_game_options_are_compact_searchable_and_cacheable(client, db):
    db.add_all(
        [
            models.Game(title="Portal", normalized_title="portal"),
            models.Game(title="Portal 2", normalized_title="portal 2"),
            models.Game(title="Quake", normalized_title="quake"),
            models.Game(
                title="VR Video Player",
                normalized_title="vr video player",
                is_game=False,
                non_game_reason="Software-Genre: utilities",
            ),
        ]
    )
    db.commit()

    response = client.get("/api/games/options?search=portal")
    assert response.status_code == 200
    assert [item["title"] for item in response.json()] == ["Portal", "Portal 2"]
    assert set(response.json()[0]) == {"id", "title"}
    assert "VR Video Player" not in {
        item["title"] for item in client.get("/api/games/options").json()
    }
    assert "VR Video Player" not in {
        item["title"] for item in client.get("/api/games").json()
    }
    assert "VR Video Player" in {
        item["title"] for item in client.get("/api/games?include_non_games=true").json()
    }
    assert response.headers["cache-control"].startswith("private, max-age=300")

    cached = client.get("/api/games/options", headers={"If-None-Match": response.headers["etag"]})
    assert cached.status_code == 304


def test_game_page_is_paginated_filtered_and_sorted_on_the_server(client, db):
    games = [
        models.Game(
            title=f"Network Game {index:03d}",
            normalized_title=f"network game {index:03d}",
            genres=["Action"] if index % 2 else ["Strategy"],
            multiplayer=True,
            min_players=1,
            max_players=8,
            player_count_known=True,
        )
        for index in range(250)
    ]
    solo = models.Game(
        title="Only Solo",
        normalized_title="only solo",
        singleplayer=True,
    )
    software = models.Game(
        title="Video Tool",
        normalized_title="video tool",
        is_game=False,
        genres=["Utilities"],
    )
    db.add_all([*games, solo, software])
    db.flush()

    participants = [
        models.Participant(nickname=f"Player {index}", present=True)
        for index in range(3)
    ]
    db.add_all(participants)
    db.flush()
    accounts = [
        models.Account(
            participant_id=participant.id,
            platform=models.Platform.steam,
            account_id=f"steam-{participant.id}",
        )
        for participant in participants
    ]
    db.add_all(accounts)
    db.flush()
    for participant, account in zip(participants, accounts, strict=True):
        db.add(
            models.Ownership(
                participant_id=participant.id,
                account_id=account.id,
                game_id=games[42].id,
                platform=models.Platform.steam,
            )
        )
    db.commit()

    second_page = client.get("/api/games/page?page=2&per_page=25")
    assert second_page.status_code == 200
    payload = second_page.json()
    assert payload["total"] == 250
    assert len(payload["items"]) == 25
    assert payload["page"] == 2
    assert payload["per_page"] == 25
    assert payload["genres"] == ["Action", "Strategy"]

    by_owners = client.get(
        "/api/games/page?per_page=25&sort_by=owner_count&sort_desc=true"
    ).json()
    assert by_owners["items"][0]["id"] == games[42].id
    assert by_owners["items"][0]["owner_count"] == 3

    searched = client.get("/api/games/page?search=game%20042").json()
    assert [item["id"] for item in searched["items"]] == [games[42].id]

    with_solo = client.get(
        "/api/games/page?include_pure_singleplayer=true&search=only%20solo"
    ).json()
    assert [item["id"] for item in with_solo["items"]] == [solo.id]

    with_software = client.get(
        "/api/games/page?include_non_games=true&search=video%20tool"
    ).json()
    assert [item["id"] for item in with_software["items"]] == [software.id]


def test_game_owners_endpoint_returns_present_deduplicated_owners(client, db):
    ada = models.Participant(nickname="Ada", present=True)
    bob = models.Participant(nickname="Bob", present=False)
    game = models.Game(title="Quake III Arena", normalized_title="quake iii arena", multiplayer=True)
    db.add_all([ada, bob, game])
    db.flush()
    ada_steam = models.Account(
        participant_id=ada.id,
        platform=models.Platform.steam,
        account_id="ada-steam",
        display_name="AdaSteam",
    )
    ada_gog = models.Account(
        participant_id=ada.id,
        platform=models.Platform.gog,
        account_id="ada-gog",
        display_name="AdaGOG",
    )
    bob_steam = models.Account(
        participant_id=bob.id,
        platform=models.Platform.steam,
        account_id="bob-steam",
        display_name="BobSteam",
    )
    db.add_all([ada_steam, ada_gog, bob_steam])
    db.flush()
    db.add_all(
        [
            models.Ownership(
                participant_id=ada.id,
                account_id=ada_steam.id,
                game_id=game.id,
                platform=models.Platform.steam,
                playtime_minutes=120,
                last_seen=datetime.utcnow(),
            ),
            models.Ownership(
                participant_id=ada.id,
                account_id=ada_gog.id,
                game_id=game.id,
                platform=models.Platform.gog,
                playtime_minutes=30,
                last_seen=datetime.utcnow(),
            ),
            models.Ownership(
                participant_id=bob.id,
                account_id=bob_steam.id,
                game_id=game.id,
                platform=models.Platform.steam,
                playtime_minutes=999,
                last_seen=datetime.utcnow(),
            ),
        ]
    )
    db.commit()

    response = client.get(f"/api/games/{game.id}/owners")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["participant"]["nickname"] == "Ada"
    assert payload[0]["platforms"] == ["gog", "steam"]
    assert payload[0]["total_playtime_minutes"] == 150

    all_response = client.get(f"/api/games/{game.id}/owners?present_only=false")
    assert [item["participant"]["nickname"] for item in all_response.json()] == ["Bob", "Ada"]


def test_account_create_reuses_participant_platform(client):
    participant = client.post("/api/participants", json={"nickname": "Lob", "present": True}).json()
    first = client.post("/api/accounts", json={"participant_id": participant["id"], "platform": "ubisoft"})
    second = client.post("/api/accounts", json={"participant_id": participant["id"], "platform": "ubisoft"})

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    assert len(client.get("/api/accounts").json()) == 1


def test_playnite_upload_streams_to_disk_and_removes_temp_file(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "playnite_upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "playnite_upload_max_bytes", 16 * 1024 * 1024)
    monkeypatch.setattr(
        imports_api,
        "run_playnite_import",
        lambda _run_id, path: Path(path).unlink(missing_ok=True),
    )
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

    assert response.status_code == 202
    assert response.json()["kind"] == "playnite"
    assert response.json()["stage"] == "queued"
    assert list(tmp_path.iterdir()) == []


def test_playnite_upload_rejects_oversized_file_and_removes_temp_file(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "playnite_upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "playnite_upload_max_bytes", 32)
    participant = client.post("/api/participants", json={"nickname": "Oversized", "present": True}).json()

    response = client.post(
        "/api/imports/playnite",
        data={"participant_id": str(participant["id"])},
        files={"file": ("too-large.zip", b"x" * 64, "application/zip")},
    )

    assert response.status_code == 413
    assert list(tmp_path.iterdir()) == []


def test_gog_galaxy_upload_streams_to_disk_and_removes_temp_file(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "playnite_upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "playnite_upload_max_bytes", 16 * 1024 * 1024)
    monkeypatch.setattr(
        imports_api,
        "run_gog_galaxy_import",
        lambda _run_id, path: Path(path).unlink(missing_ok=True),
    )
    participant = client.post("/api/participants", json={"nickname": "Galaxy", "present": True}).json()

    response = client.post(
        "/api/imports/gog-galaxy",
        data={"participant_id": str(participant["id"])},
        files={"file": ("galaxy-2.0.db", b"SQLite format 3\x00", "application/octet-stream")},
    )

    assert response.status_code == 202
    assert response.json()["kind"] == "gog_galaxy"
    assert response.json()["stage"] == "queued"
    assert list(tmp_path.iterdir()) == []
