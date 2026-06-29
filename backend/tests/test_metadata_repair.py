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
