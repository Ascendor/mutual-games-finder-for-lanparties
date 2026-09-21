import json
import sqlite3
import zipfile
from pathlib import Path

from sqlalchemy import select

from app.models import Account, Participant, Platform, PlatformGameMapping
from app.services.gog_galaxy_import import import_gog_galaxy_export_path
from app.services.import_providers import ImportedGame
from app.services.sync_service import resolve_game, upsert_ownership


def test_gog_galaxy_import_reads_library_and_reuses_direct_account(db, tmp_path):
    participant = Participant(nickname="Ada", present=True)
    db.add(participant)
    db.flush()
    steam = Account(participant_id=participant.id, platform=Platform.steam, account_id="76561198000000000")
    db.add(steam)
    db.commit()
    database = tmp_path / "galaxy-2.0.db"
    _write_galaxy_db(
        database,
        [
            ("steam_620", "Portal 2", 180),
            ("origin_OFB-EAST:48217", "Mass Effect", 90),
            ("psn_CUSA00000", "Console Only", 300),
        ],
    )

    result = import_gog_galaxy_export_path(db, participant.id, database)

    assert result.imported_games == 2
    assert result.created_accounts == 1
    assert result.platforms == ["ea", "steam"]
    assert {account.platform for account in participant.accounts} == {Platform.steam, Platform.ea}
    portal = next(own for own in participant.ownerships if own.game.title == "Portal 2")
    assert portal.account_id == steam.id
    assert portal.playtime_minutes == 180


def test_gog_galaxy_import_does_not_replace_direct_provider_playtime(db, tmp_path):
    participant = Participant(nickname="Priority", present=True)
    db.add(participant)
    db.flush()
    account = Account(participant_id=participant.id, platform=Platform.steam, account_id="76561198000000000")
    db.add(account)
    db.flush()
    game = resolve_game(db, Platform.steam, ImportedGame(platform_game_id="620", title="Portal 2"))
    upsert_ownership(db, account, game, ImportedGame(platform_game_id="620", title="Portal 2", playtime_minutes=240))
    db.commit()
    database = tmp_path / "galaxy-2.0.db"
    _write_galaxy_db(database, [("steam_620", "Portal 2", 999)])

    import_gog_galaxy_export_path(db, participant.id, database)

    assert participant.ownerships[0].playtime_minutes == 240


def test_gog_galaxy_synthetic_account_can_update_fallback_playtime(db, tmp_path):
    participant = Participant(nickname="Fallback", present=True)
    db.add(participant)
    db.commit()
    first = tmp_path / "first.db"
    second = tmp_path / "second.db"
    _write_galaxy_db(first, [("rockstar_rdr2", "Red Dead Redemption 2", 120)])
    _write_galaxy_db(second, [("rockstar_rdr2", "Red Dead Redemption 2", 180)])

    import_gog_galaxy_export_path(db, participant.id, first)
    import_gog_galaxy_export_path(db, participant.id, second)

    assert participant.ownerships[0].playtime_minutes == 180


def test_gog_galaxy_import_reads_database_from_zip(db, tmp_path):
    participant = Participant(nickname="ZipUser", present=True)
    db.add(participant)
    db.commit()
    database = tmp_path / "galaxy-2.0.db"
    _write_galaxy_db(database, [("gog_1207658645", "MDK 2", 12)])
    archive_path = tmp_path / "galaxy.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.write(database, "storage/galaxy-2.0.db")

    result = import_gog_galaxy_export_path(db, participant.id, archive_path)

    assert result.imported_games == 1
    assert result.platforms == ["gog"]
    assert participant.ownerships[0].game.title == "MDK 2"


def test_gog_galaxy_import_adds_safe_related_platform_mappings(db, tmp_path):
    participant = Participant(nickname="Mapper", present=True)
    db.add(participant)
    db.commit()
    database = tmp_path / "galaxy-2.0.db"
    _write_galaxy_db(
        database,
        [
            (
                "epic_Fowl",
                "The Escapists 2",
                15,
                ["steam_641990", "gog_2137491407", "epic_Fowl", "psn_CUSA06244_00"],
            )
        ],
    )

    import_gog_galaxy_export_path(db, participant.id, database)
    mapped = resolve_game(db, Platform.gog, ImportedGame(platform_game_id="2137491407", title="The Escapists 2"))

    assert mapped.id == participant.ownerships[0].game_id
    assert {
        (mapping.platform, mapping.platform_game_id)
        for mapping in db.scalars(select(PlatformGameMapping)).all()
    } == {
        (Platform.epic, "Fowl"),
        (Platform.steam, "641990"),
        (Platform.gog, "2137491407"),
    }


def test_gog_galaxy_related_mappings_never_rehome_existing_platform_mapping(db, tmp_path):
    existing = resolve_game(db, Platform.steam, ImportedGame(platform_game_id="123", title="Already Mapped"))
    participant = Participant(nickname="Conflict", present=True)
    db.add(participant)
    db.commit()
    database = tmp_path / "galaxy-2.0.db"
    _write_galaxy_db(database, [("gog_conflict", "Different Game", 0, ["steam_123", "gog_conflict"])])

    import_gog_galaxy_export_path(db, participant.id, database)

    steam_mapping = db.scalar(
        select(PlatformGameMapping).where(
            PlatformGameMapping.platform == Platform.steam,
            PlatformGameMapping.platform_game_id == "123",
        )
    )
    assert steam_mapping is not None
    assert steam_mapping.game_id == existing.id


def test_gog_galaxy_related_mappings_skip_ambiguous_new_steam_ids(db, tmp_path):
    participant = Participant(nickname="Ambiguous", present=True)
    db.add(participant)
    db.commit()
    database = tmp_path / "galaxy-2.0.db"
    _write_galaxy_db(
        database,
        [("gog_ambiguous", "Ambiguous Steam Game", 0, ["steam_100", "steam_200", "gog_ambiguous"])],
    )

    import_gog_galaxy_export_path(db, participant.id, database)

    steam_mappings = db.scalars(
        select(PlatformGameMapping).where(PlatformGameMapping.platform == Platform.steam)
    ).all()
    assert steam_mappings == []


def _write_galaxy_db(path: Path, rows: list[tuple]) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE LibraryReleases (id INTEGER PRIMARY KEY, userId INTEGER, releaseKey TEXT);
            CREATE TABLE LicensedReleases (libraryId INTEGER, isOwned INTEGER);
            CREATE TABLE GameTimes (userId INTEGER, releaseKey TEXT, minutesInGame INTEGER);
            CREATE TABLE GamePieces (
                releaseKey TEXT,
                gamePieceTypeId INTEGER,
                userId INTEGER,
                value TEXT,
                languageId INTEGER
            );
            CREATE TABLE GamePieceTypes (id INTEGER, type TEXT);
            """
        )
        connection.execute("INSERT INTO GamePieceTypes (id, type) VALUES (573, 'title')")
        connection.execute("INSERT INTO GamePieceTypes (id, type) VALUES (376, 'allGameReleases')")
        for index, row in enumerate(rows, start=1):
            release_key, title, playtime = row[:3]
            related_releases = row[3] if len(row) > 3 else []
            connection.execute(
                "INSERT INTO LibraryReleases (id, userId, releaseKey) VALUES (?, ?, ?)",
                (index, 1, release_key),
            )
            connection.execute(
                "INSERT INTO LicensedReleases (libraryId, isOwned) VALUES (?, 1)",
                (index,),
            )
            connection.execute(
                "INSERT INTO GameTimes (userId, releaseKey, minutesInGame) VALUES (?, ?, ?)",
                (1, release_key, playtime),
            )
            connection.execute(
                "INSERT INTO GamePieces (releaseKey, gamePieceTypeId, userId, value, languageId) VALUES (?, 573, ?, ?, NULL)",
                (release_key, 1, json.dumps({"title": title})),
            )
            if related_releases:
                connection.execute(
                    "INSERT INTO GamePieces (releaseKey, gamePieceTypeId, userId, value, languageId) VALUES (?, 376, ?, ?, NULL)",
                    (release_key, 1, json.dumps({"releases": related_releases})),
                )
