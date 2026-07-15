from datetime import datetime

from app.models import Game, Platform, PlatformGameMapping
from app.services import metadata_service
from app.services.metadata_service import MetadataRecord
from app.services.normalization import normalize_title


def test_igdb_multiplayer_modes_are_mapped_to_structured_metadata(monkeypatch):
    monkeypatch.setattr(
        metadata_service,
        "_igdb_post",
        lambda endpoint, query, token: [
            {
                "id": 620,
                "name": "Portal 2",
                "summary": "A cooperative puzzle game.",
                "genres": [{"name": "Puzzle"}],
                "game_modes": [{"name": "Single player"}, {"name": "Multiplayer"}, {"name": "Co-operative"}],
                "multiplayer_modes": [
                    {
                        "platform": {"name": "PC (Microsoft Windows)"},
                        "campaigncoop": True,
                        "dropin": False,
                        "lancoop": True,
                        "offlinecoop": True,
                        "offlinecoopmax": 2,
                        "offlinemax": 2,
                        "onlinecoop": True,
                        "onlinecoopmax": 2,
                        "onlinemax": 2,
                        "splitscreen": True,
                        "splitscreenonline": False,
                    }
                ],
            }
        ],
    )

    record = metadata_service._igdb_record("Portal 2", [Platform.steam], "token")

    assert record is not None
    assert record.primary_source == "igdb"
    assert record.values["singleplayer"] is True
    assert record.values["multiplayer"] is True
    assert record.values["campaign_coop"] is True
    assert record.values["lan"] is True
    assert record.values["split_screen"] is True
    assert record.values["offline_max_players"] == 2
    assert record.values["online_max_players"] == 2
    assert record.values["max_players"] == 2
    assert record.values["player_count_known"] is True


def test_igdb_values_override_rawg_but_rawg_fills_missing_fields():
    igdb = MetadataRecord(primary_source="igdb", external_id="620")
    igdb.set("multiplayer", True, "igdb")
    igdb.set("max_players", 2, "igdb")
    igdb.set("player_count_known", True, "igdb")
    rawg = MetadataRecord(primary_source="rawg", external_id="rawg-portal-2")
    rawg.set("multiplayer", False, "rawg")
    rawg.set("max_players", 8, "rawg")
    rawg.set("player_count_known", True, "rawg")
    rawg.set("hotseat", True, "rawg")
    rawg.set("description", "Fallback description", "rawg")

    merged = metadata_service._merge_records(igdb, rawg)

    assert merged is not None
    assert merged.values["multiplayer"] is True
    assert merged.values["max_players"] == 2
    assert merged.sources["max_players"] == "igdb"
    assert merged.values["hotseat"] is True
    assert merged.values["description"] == "Fallback description"


def test_igdb_matching_does_not_confuse_numbered_games():
    candidates = [
        {"id": 1, "name": "Alone in the Dark"},
        {"id": 2, "name": "Alone in the Dark 2"},
        {"id": 3, "name": "Alone in the Dark 3"},
    ]

    assert metadata_service._select_igdb_game("Alone in the Dark 2", candidates)["id"] == 2


def test_igdb_matching_prefers_the_owned_platform_for_identical_titles():
    candidates = [
        {"id": 266357, "name": "Counter-Strike", "platforms": [{"name": "Xbox"}]},
        {
            "id": 241,
            "name": "Counter-Strike",
            "platforms": [{"name": "PC (Microsoft Windows)"}, {"name": "Linux"}],
        },
    ]

    selected = metadata_service._select_igdb_game("Counter-Strike", candidates, [Platform.steam])

    assert selected is not None
    assert selected["id"] == 241


def test_igdb_matching_prefers_exact_external_store_id():
    candidates = [
        {
            "id": 332258,
            "name": "Quake",
            "platforms": [{"name": "PC (Microsoft Windows)"}],
        },
        {
            "id": 333,
            "name": "Quake",
            "platforms": [{"name": "PC (Microsoft Windows)"}],
            "external_games": [{"uid": "2310"}],
        },
    ]

    selected = metadata_service._select_igdb_game(
        "Quake",
        candidates,
        [Platform.steam],
        {"2310", "1435828198"},
    )

    assert selected is not None
    assert selected["id"] == 333


def test_rawg_availability_rejects_invalid_key_once(monkeypatch):
    class Response:
        status_code = 401
        is_error = True

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(metadata_service.settings, "rawg_api_key", "invalid")
    monkeypatch.setattr(metadata_service.httpx, "Client", Client)

    available, reason = metadata_service._rawg_availability()

    assert available is False
    assert reason == "nicht verfügbar (HTTP 401; Monatskontingent oder Schlüssel prüfen)"


def test_metadata_sync_applies_igdb_before_rawg(db, monkeypatch):
    game = Game(
        title="Portal 2",
        normalized_title=normalize_title("Portal 2"),
        multiplayer=False,
        min_players=1,
        max_players=1,
    )
    db.add(game)
    db.flush()
    db.add(
        PlatformGameMapping(
            game_id=game.id,
            platform=Platform.steam,
            platform_game_id="620",
            platform_title="Portal 2",
            normalized_title=game.normalized_title,
        )
    )
    db.commit()

    monkeypatch.setattr(metadata_service, "_igdb_access_token", lambda: "token")
    monkeypatch.setattr(metadata_service, "_rawg_availability", lambda: (True, None))

    def fake_fetch(job):
        record = MetadataRecord(primary_source="igdb", external_id="620")
        record.set("singleplayer", True, "igdb")
        record.set("multiplayer", True, "igdb")
        record.set("online_coop", True, "igdb")
        record.set("max_players", 2, "igdb")
        record.set("min_players", 1, "igdb")
        record.set("multiplayer_metadata_known", True, "igdb")
        record.set("player_count_known", True, "igdb")
        record.set("description", "RAWG fallback text", "rawg")
        return job[0], record, False, False

    monkeypatch.setattr(metadata_service, "_fetch_game_metadata", fake_fetch)

    result = metadata_service.enrich_all_game_metadata(db)

    assert result.updated_games == 1
    assert game.metadata_source == "igdb"
    assert game.metadata_external_id == "620"
    assert game.multiplayer is True
    assert game.online_coop is True
    assert game.max_players == 2
    assert game.player_count_known is True
    assert game.metadata_sources["max_players"] == "igdb"
    assert game.metadata_sources["description"] == "rawg"


def test_metadata_sync_preserves_sources_from_other_providers(db, monkeypatch):
    game = Game(
        title="Team Fortress 2",
        normalized_title=normalize_title("Team Fortress 2"),
        is_free=True,
        metadata_sources={"is_free": "steam_store"},
    )
    db.add(game)
    db.commit()

    monkeypatch.setattr(metadata_service, "_igdb_access_token", lambda: "token")
    monkeypatch.setattr(metadata_service, "_rawg_availability", lambda: (True, None))

    def fake_fetch(job):
        record = MetadataRecord(primary_source="igdb", external_id="440")
        record.set("multiplayer", True, "igdb")
        return job[0], record, False, False

    monkeypatch.setattr(metadata_service, "_fetch_game_metadata", fake_fetch)

    metadata_service.enrich_all_game_metadata(db, game_ids={game.id})

    assert game.metadata_sources["is_free"] == "steam_store"
    assert game.metadata_sources["multiplayer"] == "igdb"


def test_metadata_sync_soft_excludes_software_from_existing_genres(db, monkeypatch):
    game = Game(
        title="VR Video Player",
        normalized_title=normalize_title("VR Video Player"),
        genres=["Utilities", "Video Production"],
    )
    db.add(game)
    db.commit()

    monkeypatch.setattr(metadata_service, "_igdb_access_token", lambda: "token")
    monkeypatch.setattr(metadata_service, "_rawg_availability", lambda: (False, None))
    monkeypatch.setattr(
        metadata_service,
        "_fetch_game_metadata",
        lambda job: (job[0], None, False, False),
    )

    result = metadata_service.enrich_all_game_metadata(db)

    assert result.excluded_games == 1
    assert result.updated_games == 1
    assert game.is_game is False
    assert "utilities" in (game.non_game_reason or "")
    assert game.metadata_sources["is_game"] == "classification"


def test_metadata_repair_game_ids_selects_only_unknown_or_suspicious_games(db):
    good = Game(
        title="Portal 2",
        normalized_title=normalize_title("Portal 2"),
        metadata_source="igdb",
        metadata_updated_at=datetime.utcnow(),
        singleplayer=True,
        multiplayer=True,
        multiplayer_metadata_known=True,
        player_count_known=True,
        min_players=1,
        max_players=2,
    )
    unknown = Game(
        title="Unknown Multiplayer",
        normalized_title=normalize_title("Unknown Multiplayer"),
    )
    suspicious = Game(
        title="Multiplayer With Bad Player Count",
        normalized_title=normalize_title("Multiplayer With Bad Player Count"),
        metadata_source="igdb",
        metadata_updated_at=datetime.utcnow(),
        multiplayer=True,
        multiplayer_metadata_known=True,
        player_count_known=True,
        min_players=1,
        max_players=1,
    )
    bad_genres = Game(
        title="Serialized Genre Fragment",
        normalized_title=normalize_title("Serialized Genre Fragment"),
        metadata_source="igdb",
        metadata_updated_at=datetime.utcnow(),
        singleplayer=True,
        multiplayer_metadata_known=True,
        player_count_known=True,
        min_players=1,
        max_players=1,
        genres=["{'Field': 41", "Action"],
    )
    db.add_all([good, unknown, suspicious, bad_genres])
    db.commit()

    repair_ids = metadata_service.metadata_repair_game_ids(db)

    assert good.id not in repair_ids
    assert unknown.id in repair_ids
    assert suspicious.id in repair_ids
    assert bad_genres.id in repair_ids
