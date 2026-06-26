from app.models import Account, Participant, Platform, PlatformGameMapping
from app.services.import_providers import ImportedGame, _steam_metadata_from_details
from app.services.metadata_repair import repair_legacy_steam_metadata
from app.services.sync_service import resolve_game, upsert_ownership


def test_resolve_game_maps_fuzzy_titles_to_same_entity(db):
    steam = ImportedGame(platform_game_id="550", title="Left 4 Dead 2")
    epic = ImportedGame(platform_game_id="l4d2", title="Left 4 Dead(TM) 2")

    first = resolve_game(db, Platform.steam, steam)
    second = resolve_game(db, Platform.epic, epic)

    assert first.id == second.id


def test_upsert_ownership_preserves_single_row(db):
    participant = Participant(nickname="Ada")
    db.add(participant)
    db.flush()
    account = Account(participant_id=participant.id, platform=Platform.steam, account_id="42")
    db.add(account)
    db.flush()
    game = resolve_game(db, Platform.steam, ImportedGame(platform_game_id="1", title="Portal 2"))

    upsert_ownership(db, account, game, ImportedGame(platform_game_id="1", title="Portal 2", playtime_minutes=10))
    upsert_ownership(db, account, game, ImportedGame(platform_game_id="1", title="Portal 2", playtime_minutes=20))
    db.flush()

    assert len(participant.ownerships) == 1
    assert participant.ownerships[0].playtime_minutes == 20



def test_resolve_game_does_not_collapse_numbered_sequels(db):
    first = resolve_game(db, Platform.gog, ImportedGame(platform_game_id="alone1", title="Alone in the Dark 1"))
    second = resolve_game(db, Platform.gog, ImportedGame(platform_game_id="alone2", title="Alone in the Dark 2"))
    third = resolve_game(db, Platform.gog, ImportedGame(platform_game_id="alone3", title="Alone in the Dark 3"))

    assert len({first.id, second.id, third.id}) == 3


def test_resolve_game_rehomes_bad_existing_mapping_for_numbered_sequel(db):
    first = resolve_game(db, Platform.gog, ImportedGame(platform_game_id="alone1", title="Alone in the Dark 1"))
    bad_mapping_game = resolve_game(db, Platform.gog, ImportedGame(platform_game_id="alone2", title="Alone in the Dark 1"))
    corrected = resolve_game(db, Platform.gog, ImportedGame(platform_game_id="alone2", title="Alone in the Dark 2"))

    assert bad_mapping_game.id == first.id
    assert corrected.id != first.id
    assert corrected.title == "Alone in the Dark 2"


def test_steam_metadata_does_not_invent_split_screen_or_player_cap():
    metadata = _steam_metadata_from_details(
        20,
        {
            "categories": [
                {"id": 1, "description": "Multi-player"},
                {"id": 27, "description": "Cross-Platform Multiplayer"},
            ],
            "genres": [{"description": "Action"}],
        },
    )

    assert metadata["multiplayer"] is True
    assert metadata["split_screen"] is False
    assert metadata["shared_screen"] is False
    assert metadata["max_players"] == 1
    assert metadata["feature_metadata_known"] is True


def test_trusted_imported_metadata_can_clear_previous_bad_feature_guess(db):
    game = resolve_game(
        db,
        Platform.steam,
        ImportedGame(
            platform_game_id="20",
            title="Team Fortress Classic",
            multiplayer=True,
            split_screen=True,
            shared_screen=True,
            max_players=8,
        ),
    )

    corrected = resolve_game(
        db,
        Platform.steam,
        ImportedGame(
            platform_game_id="20",
            title="Team Fortress Classic",
            multiplayer=True,
            split_screen=False,
            shared_screen=False,
            max_players=1,
            feature_metadata_known=True,
        ),
    )

    assert corrected.id == game.id
    assert corrected.multiplayer is True
    assert corrected.split_screen is False
    assert corrected.shared_screen is False
    assert corrected.max_players == 1


def test_legacy_steam_metadata_repair_clears_tfc_split_and_invented_cap(db):
    game = resolve_game(
        db,
        Platform.steam,
        ImportedGame(
            platform_game_id="20",
            title="Team Fortress Classic",
            multiplayer=True,
            split_screen=True,
            shared_screen=True,
            max_players=8,
        ),
    )
    db.flush()

    changed = repair_legacy_steam_metadata(db)

    assert changed == 1
    assert game.multiplayer is True
    assert game.split_screen is False
    assert game.shared_screen is False
    assert game.max_players == 32

