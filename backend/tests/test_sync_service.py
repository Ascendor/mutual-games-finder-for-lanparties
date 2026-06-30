from app.models import Account, Participant, Platform, PlatformGameMapping
from sqlalchemy import select

from app.models import Ownership
from app.services.import_providers import ImportedGame, _steam_metadata_from_details
from app.services.sync_service import _reconcile_account_ownerships, resolve_game, upsert_ownership


def test_resolve_game_maps_fuzzy_titles_to_same_entity(db):
    steam = ImportedGame(platform_game_id="550", title="Left 4 Dead 2")
    epic = ImportedGame(platform_game_id="l4d2", title="Left 4 Dead(TM) 2")

    first = resolve_game(db, Platform.steam, steam)
    second = resolve_game(db, Platform.epic, epic)

    assert first.id == second.id


def test_resolve_game_never_merges_different_steam_app_ids(db):
    first = resolve_game(db, Platform.steam, ImportedGame(platform_game_id="100", title="Identical Title"))
    second = resolve_game(db, Platform.steam, ImportedGame(platform_game_id="200", title="Identical Title"))

    assert first.id != second.id


def test_resolve_game_may_merge_synthetic_playnite_id_with_numeric_steam_id(db):
    direct = resolve_game(db, Platform.steam, ImportedGame(platform_game_id="100", title="Same Game"))
    playnite = resolve_game(
        db,
        Platform.steam,
        ImportedGame(platform_game_id="playnite:same-game", title="Same Game"),
    )

    assert direct.id == playnite.id


def test_resolve_game_does_not_merge_base_title_subtitle_or_roman_sequels(db):
    legend = resolve_game(db, Platform.steam, ImportedGame(platform_game_id="7000", title="Tomb Raider: Legend"))
    reboot = resolve_game(db, Platform.steam, ImportedGame(platform_game_id="203160", title="Tomb Raider"))
    first = resolve_game(db, Platform.steam, ImportedGame(platform_game_id="224960", title="Tomb Raider I"))
    second = resolve_game(db, Platform.steam, ImportedGame(platform_game_id="225300", title="Tomb Raider II"))

    assert len({legend.id, reboot.id, first.id, second.id}) == 4


def test_resolve_game_rehomes_existing_mapping_from_wrong_subtitle(db):
    legend = resolve_game(db, Platform.steam, ImportedGame(platform_game_id="7000", title="Tomb Raider: Legend"))
    bad_mapping = PlatformGameMapping(
        game_id=legend.id,
        platform=Platform.steam,
        platform_game_id="203160",
        platform_title="Tomb Raider",
        normalized_title="tomb raider",
    )
    db.add(bad_mapping)
    db.flush()

    corrected = resolve_game(db, Platform.steam, ImportedGame(platform_game_id="203160", title="Tomb Raider"))

    assert corrected.id != legend.id
    assert corrected.title == "Tomb Raider"
    assert bad_mapping.game_id == corrected.id


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


def test_upsert_ownership_does_not_replace_known_playtime_with_zero(db):
    participant = Participant(nickname="Grace")
    db.add(participant)
    db.flush()
    account = Account(participant_id=participant.id, platform=Platform.steam, account_id="99")
    db.add(account)
    db.flush()
    game = resolve_game(db, Platform.steam, ImportedGame(platform_game_id="620", title="Portal 2"))

    upsert_ownership(db, account, game, ImportedGame(platform_game_id="620", title="Portal 2", playtime_minutes=240))
    upsert_ownership(db, account, game, ImportedGame(platform_game_id="620", title="Portal 2", playtime_minutes=0))
    db.flush()

    assert participant.ownerships[0].playtime_minutes == 240


def test_upsert_ownership_treats_legacy_null_playtime_as_zero(db):
    participant = Participant(nickname="Legacy")
    db.add(participant)
    db.flush()
    account = Account(participant_id=participant.id, platform=Platform.steam, account_id="legacy")
    db.add(account)
    db.flush()
    game = resolve_game(db, Platform.steam, ImportedGame(platform_game_id="550", title="Left 4 Dead 2"))
    ownership = upsert_ownership(db, account, game, ImportedGame(platform_game_id="550", title="Left 4 Dead 2", playtime_minutes=0))
    ownership.playtime_minutes = None  # type: ignore[assignment]

    upsert_ownership(db, account, game, ImportedGame(platform_game_id="550", title="Left 4 Dead 2", playtime_minutes=25))
    db.flush()

    assert ownership.playtime_minutes == 25


def test_authoritative_library_reconciliation_removes_only_stale_account_ownerships(db):
    participant = Participant(nickname="Snapshot")
    db.add(participant)
    db.flush()
    account = Account(participant_id=participant.id, platform=Platform.steam, account_id="snapshot")
    db.add(account)
    db.flush()
    current = resolve_game(db, Platform.steam, ImportedGame(platform_game_id="1", title="Current"))
    stale = resolve_game(db, Platform.steam, ImportedGame(platform_game_id="2", title="Stale"))
    upsert_ownership(db, account, current, ImportedGame(platform_game_id="1", title="Current"))
    upsert_ownership(db, account, stale, ImportedGame(platform_game_id="2", title="Stale"))
    db.flush()

    _reconcile_account_ownerships(db, account, {current.id})
    db.flush()

    ownerships = db.scalars(select(Ownership).where(Ownership.account_id == account.id)).all()
    assert [ownership.game_id for ownership in ownerships] == [current.id]


def test_authoritative_library_reconciliation_keeps_known_free_games(db):
    participant = Participant(nickname="Free Snapshot")
    db.add(participant)
    db.flush()
    account = Account(participant_id=participant.id, platform=Platform.steam, account_id="free-snapshot")
    db.add(account)
    db.flush()
    free_game = resolve_game(
        db,
        Platform.steam,
        ImportedGame(platform_game_id="440", title="Free Arena", is_free=True),
    )
    upsert_ownership(
        db,
        account,
        free_game,
        ImportedGame(platform_game_id="440", title="Free Arena", is_free=True),
    )
    db.flush()

    _reconcile_account_ownerships(db, account, set())
    db.flush()

    ownership = db.scalar(select(Ownership).where(Ownership.account_id == account.id))
    assert ownership is not None
    assert ownership.game.is_free is True


def test_resolve_game_tolerates_missing_imported_player_counts(db):
    imported = ImportedGame(platform_game_id="broken-meta", title="Broken Metadata")
    imported.min_players = None  # type: ignore[assignment]
    imported.max_players = None  # type: ignore[assignment]

    game = resolve_game(db, Platform.steam, imported)

    assert game.min_players == 1
    assert game.max_players == 1



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
    assert metadata["player_count_known"] is False


def test_steam_metadata_marks_only_free_store_games_as_free():
    free_game = _steam_metadata_from_details(440, {"type": "game", "is_free": True})
    demo = _steam_metadata_from_details(999, {"type": "demo", "is_free": True})

    assert free_game["is_free"] is True
    assert demo["is_free"] is False


def test_provider_partial_metadata_does_not_overwrite_igdb_fields(db):
    game = resolve_game(
        db,
        Platform.steam,
        ImportedGame(platform_game_id="550", title="Left 4 Dead"),
    )
    game.multiplayer = True
    game.online_coop = True
    game.max_players = 4
    game.player_count_known = True
    game.metadata_sources = {
        "multiplayer": "igdb",
        "online_coop": "igdb",
        "max_players": "igdb",
        "player_count_known": "igdb",
    }

    merged = resolve_game(
        db,
        Platform.steam,
        ImportedGame(
            platform_game_id="550",
            title="Left 4 Dead",
            multiplayer=True,
            online_coop=False,
            min_players=1,
            max_players=1,
            feature_metadata_known=True,
            player_count_known=False,
        ),
    )

    assert merged.multiplayer is True
    assert merged.online_coop is True
    assert merged.max_players == 4
    assert merged.player_count_known is True


def test_trusted_imported_metadata_can_clear_previous_bad_feature_guess(db):
    game = resolve_game(
        db,
        Platform.steam,
        ImportedGame(
            platform_game_id="example-multiplayer",
            title="Example Multiplayer",
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
            platform_game_id="example-multiplayer",
            title="Example Multiplayer",
            multiplayer=True,
            split_screen=False,
            shared_screen=False,
            max_players=1,
            feature_metadata_known=True,
            player_count_known=True,
        ),
    )

    assert corrected.id == game.id
    assert corrected.multiplayer is True
    assert corrected.split_screen is False
    assert corrected.shared_screen is False
    assert corrected.max_players == 1

