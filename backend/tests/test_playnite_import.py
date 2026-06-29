import json
import struct
import uuid
import zipfile
from io import BytesIO

from app.models import Account, Participant, Platform
from app.services.playnite_import import import_playnite_export


def test_playnite_import_reuses_direct_platform_account_and_avoids_duplicates(db):
    participant = Participant(nickname="Ada", present=True)
    db.add(participant)
    db.flush()
    steam = Account(participant_id=participant.id, platform=Platform.steam, account_id="76561198000000000")
    db.add(steam)
    db.commit()

    payload = {
        "Games": [
            {"Name": "Portal 2", "Source": {"Name": "Steam"}, "SteamAppId": 620, "Playtime": 7200},
            {"Name": "Portal 2", "Source": {"Name": "Steam"}, "SteamAppId": 620, "Playtime": 10800},
            {"Name": "Couch Prototype", "Source": {"Name": "Manual"}, "GameId": "local-guid"},
        ]
    }

    result = import_playnite_export(db, participant.id, json.dumps(payload))

    assert result.imported_games == 3
    assert result.created_accounts == 1
    assert {account.platform for account in participant.accounts} == {Platform.steam, Platform.local}
    assert len(participant.ownerships) == 2
    portal = next(own for own in participant.ownerships if own.game.title == "Portal 2")
    assert portal.account_id == steam.id
    assert portal.playtime_minutes == 180


def test_playnite_import_keeps_supported_non_direct_platforms(db):
    participant = Participant(nickname="Linus", present=True)
    db.add(participant)
    db.commit()

    payload = {
        "Games": [
            {"Name": "Diablo IV", "Source": {"Name": "Battle.net"}, "BattleNetId": "fenris", "Playtime": "01:30:00"},
            {"Name": "Celeste Classic", "Source": {"Name": "itch.io"}, "Url": "https://example.itch.io/celeste-classic"},
        ]
    }

    result = import_playnite_export(db, participant.id, json.dumps(payload))

    assert result.platforms == ["battle_net", "itch"]
    assert {account.platform for account in participant.accounts} == {Platform.battle_net, Platform.itch}
    diablo = next(own for own in participant.ownerships if own.game.title == "Diablo IV")
    assert diablo.playtime_minutes == 90


def test_playnite_import_reads_backup_zip(db):
    participant = Participant(nickname="Grace", present=True)
    db.add(participant)
    db.commit()
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("config/settings.json", json.dumps({"Theme": "Default"}))
        archive.writestr(
            "library/games.json",
            json.dumps({"Games": [{"Name": "Control", "Source": {"Name": "Amazon Games"}, "ProductId": "control-amazon"}]}),
        )

    result = import_playnite_export(db, participant.id, buffer.getvalue())

    assert result.imported_games == 1
    assert result.platforms == ["amazon"]
    assert participant.ownerships[0].game.title == "Control"


def test_playnite_import_recurses_past_named_backup_containers(db):
    participant = Participant(nickname="Ada2", present=True)
    db.add(participant)
    db.commit()
    payload = {
        "Name": "Playnite Backup",
        "Items": [
            {
                "Name": "Library Container",
                "Games": [
                    {"Name": "Portal", "Source": {"Name": "Steam"}, "SteamAppId": 400},
                    {"Name": "Portal 2", "Source": {"Name": "Steam"}, "SteamAppId": 620},
                ],
            }
        ],
    }

    result = import_playnite_export(db, participant.id, json.dumps(payload))

    assert result.imported_games == 2
    assert sorted(ownership.game.title for ownership in participant.ownerships) == ["Portal", "Portal 2"]


def test_playnite_import_reads_playnite_library_databases(db):
    participant = Participant(nickname="BackupUser", present=True)
    db.add(participant)
    db.commit()

    steam_source = uuid.uuid4()
    steam_platform = uuid.uuid4()
    action_genre = uuid.uuid4()
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("library/sources.db", _bson_db([{"Id": steam_source, "Name": "Steam"}]))
        archive.writestr("library/platforms.db", _bson_db([{"Id": steam_platform, "Name": "PC (Windows)"}]))
        archive.writestr("library/genres.db", _bson_db([{"Id": action_genre, "Name": "Action"}]))
        archive.writestr(
            "library/games.db",
            _bson_db(
                [
                    {
                        "Id": uuid.uuid4(),
                        "Name": "Portal",
                        "GameId": "400",
                        "SourceId": steam_source,
                        "PlatformIds": [steam_platform],
                        "GenreIds": [action_genre],
                        "Playtime": 7_200,
                    },
                    {
                        "Id": uuid.uuid4(),
                        "Name": "Portal 2",
                        "GameId": "620",
                        "SourceId": steam_source,
                        "PlatformIds": [steam_platform],
                        "GenreIds": [action_genre],
                        "Playtime": 18_000,
                    },
                ]
            ),
        )

    result = import_playnite_export(db, participant.id, buffer.getvalue())

    assert result.imported_games == 2
    assert result.platforms == ["steam"]
    assert sorted(ownership.game.title for ownership in participant.ownerships) == ["Portal", "Portal 2"]
    assert sorted(ownership.playtime_minutes for ownership in participant.ownerships) == [120, 300]


def test_playnite_import_ignores_truncated_litedb_false_positives(db):
    participant = Participant(nickname="NoCrash", present=True)
    db.add(participant)
    db.commit()

    source = uuid.uuid4()
    truncated_boolean_document = struct.pack("<i", 12) + b"\x08Flag\x00" + b"\x00"
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("library/sources.db", truncated_boolean_document + _bson_db([{"Id": source, "Name": "GOG"}]))
        archive.writestr(
            "library/games.db",
            _bson_db([{"Id": uuid.uuid4(), "Name": "Alone in the Dark", "GameId": "120765", "SourceId": source}]),
        )

    result = import_playnite_export(db, participant.id, buffer.getvalue())

    assert result.imported_games == 1
    assert result.platforms == ["gog"]


def test_playnite_import_ignores_object_values_misread_as_titles(db):
    participant = Participant(nickname="CleanTitles", present=True)
    db.add(participant)
    db.commit()

    payload = {
        "Games": [
            {
                "Name": {"Field": 55, "Visible": True, "Width": 374.5},
                "GameId": "layout-setting",
                "Source": {"Name": "Manual"},
            },
            {
                "Name": "while True: learn()",
                "GameId": "real-game",
                "Source": {"Name": "Steam"},
            },
        ]
    }

    result = import_playnite_export(db, participant.id, json.dumps(payload))

    assert result.imported_games == 1
    assert result.skipped_games == 0
    assert [ownership.game.title for ownership in participant.ownerships] == ["while True: learn()"]


def test_playnite_import_reads_bson_dates_as_milliseconds(db):
    participant = Participant(nickname="BsonDate", present=True)
    db.add(participant)
    db.commit()

    added_at_ms = 1_719_050_400_000
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "library/games.db",
            _bson_db(
                [
                    {
                        "Id": uuid.uuid4(),
                        "Name": "Portal",
                        "GameId": "400",
                        "Added": ("bson_datetime", added_at_ms),
                    }
                ]
            ),
        )

    result = import_playnite_export(db, participant.id, buffer.getvalue())

    assert result.imported_games == 1
    assert participant.ownerships[0].owned_since.year == 2024


def test_playnite_import_reads_games_from_litedb_extend_pages(db):
    participant = Participant(nickname="Extended", present=True)
    db.add(participant)
    db.commit()

    document = _bson_document(
        {
            "Id": uuid.uuid4(),
            "Name": "A Game With Lots Of Metadata",
            "GameId": "large-1",
            "Description": "x" * 5000,
        }
    )
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("library/games.db", _litedb_v4_with_extended_document(document))

    result = import_playnite_export(db, participant.id, buffer.getvalue())

    assert result.imported_games == 1
    assert participant.ownerships[0].game.title == "A Game With Lots Of Metadata"


def _bson_db(documents):
    return b"NOISE" + b"".join(_bson_document(document) + b"PAD" for document in documents)


def _bson_document(document):
    body = b""
    for key, value in document.items():
        body += _bson_element(key, value)
    size = len(body) + 5
    return struct.pack("<i", size) + body + b"\x00"


def _bson_element(key, value):
    name = key.encode("utf-8") + b"\x00"
    if isinstance(value, uuid.UUID):
        return b"\x05" + name + struct.pack("<i", 16) + b"\x04" + value.bytes
    if isinstance(value, str):
        encoded = value.encode("utf-8") + b"\x00"
        return b"\x02" + name + struct.pack("<i", len(encoded)) + encoded
    if isinstance(value, int):
        return b"\x12" + name + struct.pack("<q", value)
    if isinstance(value, list):
        return b"\x04" + name + _bson_document({str(index): item for index, item in enumerate(value)})
    if isinstance(value, tuple) and value[0] == "bson_datetime":
        return b"\x09" + name + struct.pack("<q", value[1])
    raise TypeError(value)


def _litedb_v4_with_extended_document(document):
    page_size = 4096
    chunks = [document[index : index + page_size - 25] for index in range(0, len(document), page_size - 25)]
    data_page = bytearray(page_size)
    struct.pack_into("<IBIIHH", data_page, 0, 0, 4, 0xFFFFFFFF, 0xFFFFFFFF, 1, page_size - 33)
    struct.pack_into("<HIH", data_page, 25, 0, 1, 0)
    pages = [bytes(data_page)]
    for index, chunk in enumerate(chunks):
        page = bytearray(page_size)
        page_id = index + 1
        next_page_id = page_id + 1 if index + 1 < len(chunks) else 0xFFFFFFFF
        struct.pack_into(
            "<IBIIHH",
            page,
            0,
            page_id,
            5,
            page_id - 1 if index else 0xFFFFFFFF,
            next_page_id,
            len(chunk),
            page_size - 25 - len(chunk),
        )
        page[25 : 25 + len(chunk)] = chunk
        pages.append(bytes(page))
    return b"".join(pages)
