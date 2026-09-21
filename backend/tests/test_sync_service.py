from datetime import datetime

from sqlalchemy import select

from app.models import Account, Ownership, Participant, Platform, PlatformGameMapping
from app.services import sync_service
from app.services.import_providers import ImportBatch, ImportedGame, _is_non_game_steam_entry, _steam_metadata_from_details
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


def test_upsert_ownership_only_accepts_sourced_acquisition_dates(db):
    participant = Participant(nickname="Dates")
    db.add(participant)
    db.flush()
    account = Account(participant_id=participant.id, platform=Platform.gog, account_id="dates")
    db.add(account)
    db.flush()
    game = resolve_game(db, Platform.gog, ImportedGame(platform_game_id="1", title="Reliable Date"))

    upsert_ownership(
        db,
        account,
        game,
        ImportedGame(platform_game_id="1", title="Reliable Date", owned_since=datetime(2025, 1, 1)),
    )
    assert participant.ownerships[0].owned_since is None

    upsert_ownership(
        db,
        account,
        game,
        ImportedGame(
            platform_game_id="1",
            title="Reliable Date",
            owned_since=datetime(2024, 1, 1),
            owned_since_source="gog_entitlement",
        ),
    )
    assert participant.ownerships[0].owned_since == datetime(2024, 1, 1)
    assert participant.ownerships[0].owned_since_source == "gog_entitlement"


def test_upsert_ownership_tracks_first_seen_and_copies_it_across_platforms(db):
    participant = Participant(nickname="Discovery")
    db.add(participant)
    db.flush()
    steam = Account(participant_id=participant.id, platform=Platform.steam, account_id="steam")
    gog = Account(participant_id=participant.id, platform=Platform.gog, account_id="gog")
    db.add_all([steam, gog])
    db.flush()
    game = resolve_game(db, Platform.steam, ImportedGame(platform_game_id="10", title="Detected Game"))

    first = upsert_ownership(db, steam, game, ImportedGame(platform_game_id="10", title="Detected Game"))
    second = upsert_ownership(db, gog, game, ImportedGame(platform_game_id="20", title="Detected Game"))
    db.flush()

    assert first.first_seen_at is not None
    assert second.first_seen_at == first.first_seen_at
    assert second.first_seen_is_baseline is False


def test_upsert_ownership_can_mark_initial_import_as_baseline(db):
    participant = Participant(nickname="Baseline")
    db.add(participant)
    db.flush()
    account = Account(participant_id=participant.id, platform=Platform.steam, account_id="steam")
    db.add(account)
    db.flush()
    game = resolve_game(db, Platform.steam, ImportedGame(platform_game_id="10", title="Baseline Game"))

    ownership = upsert_ownership(
        db,
        account,
        game,
        ImportedGame(platform_game_id="10", title="Baseline Game"),
        discovery_is_baseline=True,
    )

    assert ownership.first_seen_at is not None
    assert ownership.first_seen_is_baseline is True


def test_playnite_fallback_playtime_does_not_replace_direct_provider_time(db):
    participant = Participant(nickname="Priority")
    db.add(participant)
    db.flush()
    account = Account(participant_id=participant.id, platform=Platform.steam, account_id="76561198000000000")
    db.add(account)
    db.flush()
    game = resolve_game(db, Platform.steam, ImportedGame(platform_game_id="620", title="Portal 2"))

    upsert_ownership(db, account, game, ImportedGame(platform_game_id="620", title="Portal 2", playtime_minutes=240))
    upsert_ownership(
        db,
        account,
        game,
        ImportedGame(platform_game_id="620", title="Portal 2", playtime_minutes=999),
        playtime_priority="fallback",
    )
    db.flush()

    assert participant.ownerships[0].playtime_minutes == 240


def test_direct_provider_playtime_replaces_playnite_fallback_time(db):
    participant = Participant(nickname="Priority")
    db.add(participant)
    db.flush()
    account = Account(participant_id=participant.id, platform=Platform.steam, account_id="76561198000000000")
    db.add(account)
    db.flush()
    game = resolve_game(db, Platform.steam, ImportedGame(platform_game_id="620", title="Portal 2"))

    upsert_ownership(
        db,
        account,
        game,
        ImportedGame(platform_game_id="620", title="Portal 2", playtime_minutes=90),
        playtime_priority="fallback",
    )
    upsert_ownership(db, account, game, ImportedGame(platform_game_id="620", title="Portal 2", playtime_minutes=240))
    db.flush()

    assert participant.ownerships[0].playtime_minutes == 240


def test_playnite_owned_account_can_update_playnite_playtime(db):
    participant = Participant(nickname="Fallback")
    db.add(participant)
    db.flush()
    account = Account(participant_id=participant.id, platform=Platform.rockstar, account_id="playnite:1:rockstar")
    db.add(account)
    db.flush()
    game = resolve_game(db, Platform.rockstar, ImportedGame(platform_game_id="rdr2", title="Red Dead Redemption 2"))

    upsert_ownership(
        db,
        account,
        game,
        ImportedGame(platform_game_id="rdr2", title="Red Dead Redemption 2", playtime_minutes=120),
        playtime_priority="fallback",
    )
    upsert_ownership(
        db,
        account,
        game,
        ImportedGame(platform_game_id="rdr2", title="Red Dead Redemption 2", playtime_minutes=180),
        playtime_priority="fallback",
    )
    db.flush()

    assert participant.ownerships[0].playtime_minutes == 180


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


def test_incomplete_provider_snapshot_keeps_ownerships_for_skipped_products(db, monkeypatch):
    participant = Participant(nickname="Partial GOG")
    db.add(participant)
    db.flush()
    account = Account(
        participant_id=participant.id,
        platform=Platform.gog,
        account_id="partial-gog",
    )
    db.add(account)
    db.flush()
    current = resolve_game(
        db,
        Platform.gog,
        ImportedGame(platform_game_id="101", title="Stardew Valley"),
    )
    unresolved = resolve_game(
        db,
        Platform.gog,
        ImportedGame(platform_game_id="1173343803", title="Existing Resolved Title"),
    )
    upsert_ownership(
        db,
        account,
        current,
        ImportedGame(platform_game_id="101", title="Stardew Valley"),
    )
    upsert_ownership(
        db,
        account,
        unresolved,
        ImportedGame(platform_game_id="1173343803", title="Existing Resolved Title"),
    )
    db.commit()

    class PartialProvider:
        authoritative_library = True

        def sync_account(self, _account):
            return ImportBatch(
                games=[ImportedGame(platform_game_id="101", title="Stardew Valley")],
                warnings=["GOG-Produkt 1173343803 wurde übersprungen"],
                authoritative_snapshot=False,
            )

    monkeypatch.setitem(sync_service.PROVIDERS, Platform.gog, PartialProvider())
    run = sync_service.sync_account(db, account.id)

    ownerships = db.scalars(
        select(Ownership).where(Ownership.account_id == account.id)
    ).all()
    assert run.success is True
    assert run.imported_games == 1
    assert "1 warning" in run.message
    assert {ownership.game_id for ownership in ownerships} == {current.id, unresolved.id}


def test_direct_humble_key_reuses_playnite_ownership_and_can_reconcile_it(db):
    participant = Participant(nickname="Key Snapshot")
    db.add(participant)
    db.flush()
    playnite_account = Account(
        participant_id=participant.id,
        platform=Platform.humble_key,
        account_id="playnite:key",
    )
    direct_account = Account(
        participant_id=participant.id,
        platform=Platform.humble,
        account_id="humble-direct",
    )
    db.add_all([playnite_account, direct_account])
    db.flush()
    imported = ImportedGame(
        platform_game_id="walking-dead-key",
        title="The Walking Dead",
    )
    game = resolve_game(db, Platform.humble_key, imported)
    upsert_ownership(db, playnite_account, game, imported)
    db.flush()

    direct_import = ImportedGame(
        platform_game_id="order:1:walking-dead",
        title="The Walking Dead",
        mapping_platform=Platform.humble_key,
        ownership_platform=Platform.humble_key,
    )
    direct_game = resolve_game(db, Platform.humble_key, direct_import)
    upsert_ownership(db, direct_account, direct_game, direct_import)
    db.flush()

    ownerships = db.scalars(select(Ownership).where(Ownership.participant_id == participant.id)).all()
    assert len(ownerships) == 1
    assert ownerships[0].platform == Platform.humble_key
    assert ownerships[0].account_id == direct_account.id

    _reconcile_account_ownerships(db, direct_account, set(), Platform.humble_key)
    db.flush()
    assert db.scalar(select(Ownership).where(Ownership.participant_id == participant.id)) is None


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


def test_steam_non_game_filter_uses_store_type_and_unambiguous_titles():
    assert _is_non_game_steam_entry("DEFCON Beta Demo", {}) is True
    assert _is_non_game_steam_entry("Game Tool", {"store_type": "tool"}) is True
    assert _is_non_game_steam_entry(
        "VR Video Player",
        {"store_type": "game", "genres": ["Utilities", "Video Production"]},
    ) is True
    assert _is_non_game_steam_entry("Demeo", {}) is False
    assert _is_non_game_steam_entry("The Finals Playtest", {}) is False


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

