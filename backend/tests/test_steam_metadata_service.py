from app.models import Account, Game, Ownership, Participant, Platform, PlatformGameMapping
from app.services.normalization import normalize_title
from app.services.steam_metadata_service import _apply_steam_metadata, _steam_games


def _mapped_game(db, title: str, app_id: str) -> Game:
    game = Game(title=title, normalized_title=normalize_title(title))
    db.add(game)
    db.flush()
    db.add(
        PlatformGameMapping(
            game_id=game.id,
            platform=Platform.steam,
            platform_game_id=app_id,
            platform_title=title,
            normalized_title=game.normalized_title,
        )
    )
    db.flush()
    return game


def test_full_steam_metadata_list_uses_numeric_app_ids_and_playtime_priority(db):
    participant = Participant(nickname="Ada", present=True)
    db.add(participant)
    db.flush()
    account = Account(
        participant_id=participant.id,
        platform=Platform.steam,
        account_id="steam-ada",
    )
    db.add(account)
    db.flush()
    played = _mapped_game(db, "Played", "440")
    unplayed = _mapped_game(db, "Unplayed", "550")
    _mapped_game(db, "Synthetic Playnite Entry", "playnite-synthetic")
    db.add(
        Ownership(
            participant_id=participant.id,
            account_id=account.id,
            game_id=played.id,
            platform=Platform.steam,
            playtime_minutes=900,
        )
    )
    db.commit()

    result = _steam_games(db)

    assert result == [
        (played.id, 440, "Played"),
        (unplayed.id, 550, "Unplayed"),
    ]


def test_steam_metadata_fills_store_data_without_overwriting_igdb_features(db):
    game = _mapped_game(db, "Team Fortress 2", "440")
    game.multiplayer = True
    game.max_players = 32
    game.player_count_known = True
    game.metadata_source = "igdb"
    game.metadata_external_id = "1234"
    game.metadata_sources = {
        "multiplayer": "igdb",
        "max_players": "igdb",
        "player_count_known": "igdb",
    }
    db.commit()

    _apply_steam_metadata(
        game,
        440,
        {
            "description": "Steam description",
            "genres": ["Action", "Free to Play"],
            "store_type": "game",
            "is_free": True,
            "singleplayer": False,
            "multiplayer": False,
            "lan": False,
            "local_coop": False,
            "online_coop": False,
            "split_screen": False,
            "shared_screen": False,
            "min_players": 1,
            "max_players": 1,
            "feature_metadata_known": True,
            "player_count_known": False,
        },
    )

    assert game.is_free is True
    assert game.metadata_sources["is_free"] == "steam_store"
    assert game.multiplayer is True
    assert game.max_players == 32
    assert game.player_count_known is True
    assert game.metadata_sources["multiplayer"] == "igdb"
    assert game.metadata_source == "igdb"
    assert game.metadata_external_id == "1234"
    assert game.metadata_updated_at is not None
