from app.models import Game, Platform, PlatformGameMapping
from app.services import metadata_service
from app.services.normalization import normalize_title


def test_rawg_metadata_does_not_override_trusted_steam_features(db, monkeypatch):
    game = Game(
        title="Portal",
        normalized_title=normalize_title("Portal"),
        multiplayer=True,
        min_players=1,
        max_players=8,
    )
    db.add(game)
    db.flush()
    db.add(PlatformGameMapping(game_id=game.id, platform=Platform.steam, platform_game_id="400", platform_title="Portal", normalized_title=game.normalized_title))
    db.commit()

    monkeypatch.setattr(
        metadata_service,
        "_steam_appdetails",
        lambda appid: {
            "singleplayer": True,
            "multiplayer": False,
            "lan": False,
            "local_coop": False,
            "online_coop": False,
            "hotseat": False,
            "split_screen": False,
            "shared_screen": False,
            "min_players": 1,
            "max_players": 1,
            "feature_metadata_known": True,
        },
    )
    monkeypatch.setattr(
        metadata_service,
        "_rawg_metadata",
        lambda title: {
            "description": "RAWG description",
            "multiplayer": True,
            "max_players": 8,
            "feature_metadata_known": True,
        },
    )

    result = metadata_service.enrich_all_game_metadata(db)

    assert result.updated_games == 1
    assert game.description == "RAWG description"
    assert game.singleplayer is True
    assert game.multiplayer is False
    assert game.max_players == 1
