from datetime import datetime, timedelta

from app.api.ownerships import participant_games, recent_acquisitions
from app.models import Account, Game, Ownership, Participant, Platform


def test_participant_games_groups_platforms_and_searches(db):
    participant = Participant(nickname="PlayerOne")
    other = Participant(nickname="PlayerTwo")
    portal = Game(
        title="Portal",
        normalized_title="portal",
        genres=["Puzzle"],
        singleplayer=True,
        player_count_known=True,
        min_players=1,
        max_players=1,
    )
    half_life = Game(
        title="Half-Life",
        normalized_title="half life",
        genres=["Action"],
        multiplayer=True,
        lan=True,
        player_count_known=True,
        min_players=1,
        max_players=32,
    )
    quake = Game(title="Quake", normalized_title="quake", multiplayer=True)
    db.add_all([participant, other, portal, half_life, quake])
    db.flush()
    steam = Account(
        participant_id=participant.id,
        platform=Platform.steam,
        account_id="steam-1",
        display_name="PlayerOne on Steam",
    )
    gog = Account(
        participant_id=participant.id,
        platform=Platform.gog,
        account_id="gog-1",
        display_name="PlayerOne on GOG",
    )
    db.add_all([steam, gog])
    db.flush()
    db.add_all(
        [
            Ownership(
                participant_id=participant.id,
                account_id=steam.id,
                game_id=portal.id,
                platform=Platform.steam,
                playtime_minutes=90,
            ),
            Ownership(
                participant_id=participant.id,
                account_id=gog.id,
                game_id=portal.id,
                platform=Platform.gog,
                playtime_minutes=15,
            ),
            Ownership(
                participant_id=participant.id,
                account_id=steam.id,
                game_id=half_life.id,
                platform=Platform.steam,
                playtime_minutes=30,
            ),
            Ownership(
                participant_id=other.id,
                game_id=quake.id,
                platform=Platform.steam,
            ),
        ]
    )
    db.commit()

    result = participant_games(
        participant.id,
        search="portal",
        page=1,
        per_page=25,
        sort_by="title",
        sort_desc=False,
        db=db,
    )

    assert result["total"] == 1
    assert result["items"][0]["game"].id == portal.id
    assert result["items"][0]["total_playtime_minutes"] == 105
    assert [item["platform"] for item in result["items"][0]["platforms"]] == [
        Platform.gog,
        Platform.steam,
    ]
    assert result["items"][0]["platforms"][1]["account_display_name"] == "PlayerOne on Steam"
    assert result["platforms"] == [Platform.gog, Platform.steam]
    assert result["genres"] == ["Action", "Puzzle"]

    filtered = participant_games(
        participant.id,
        search="",
        page=1,
        per_page=25,
        sort_by="title",
        sort_desc=False,
        db=db,
        platforms=[Platform.gog],
    )

    assert filtered["total"] == 1
    assert filtered["items"][0]["game"].title == "Portal"
    assert [item["platform"] for item in filtered["items"][0]["platforms"]] == [
        Platform.gog,
        Platform.steam,
    ]

    action_games = participant_games(participant.id, db=db, genres=["Action"])
    assert action_games["total"] == 1
    assert action_games["items"][0]["game"].title == "Half-Life"

    lan_games = participant_games(participant.id, db=db, modes=["lan"])
    assert lan_games["total"] == 1
    assert lan_games["items"][0]["game"].title == "Half-Life"

    four_player_games = participant_games(participant.id, db=db, player_count=4)
    assert four_player_games["total"] == 1
    assert four_player_games["items"][0]["game"].title == "Half-Life"


def test_recent_acquisitions_prefer_store_dates_and_include_non_baseline_discoveries(db):
    now = datetime.utcnow()
    lob = Participant(nickname="PlayerOne")
    reactionman = Participant(nickname="PlayerTwo")
    old_game = Game(title="Old Game", normalized_title="old game", multiplayer=True)
    new_game = Game(title="Fresh Game", normalized_title="fresh game", multiplayer=True)
    detected_game = Game(title="Newly Detected", normalized_title="newly detected", multiplayer=True)
    import_only = Game(title="Just Imported", normalized_title="just imported", multiplayer=True)
    tool = Game(title="Video Tool", normalized_title="video tool", is_game=False)
    db.add_all([lob, reactionman, old_game, new_game, detected_game, import_only, tool])
    db.flush()
    steam = Account(participant_id=lob.id, platform=Platform.steam, account_id="steam", display_name="Steam")
    gog = Account(participant_id=lob.id, platform=Platform.gog, account_id="gog", display_name="GOG")
    db.add_all([steam, gog])
    db.flush()
    db.add_all(
        [
            Ownership(
                participant_id=lob.id,
                account_id=steam.id,
                game_id=old_game.id,
                platform=Platform.steam,
                owned_since=now - timedelta(days=500),
                owned_since_source="store_entitlement",
                last_seen=now,
            ),
            Ownership(
                participant_id=lob.id,
                account_id=gog.id,
                game_id=old_game.id,
                platform=Platform.gog,
                owned_since=now - timedelta(days=5),
                owned_since_source="store_entitlement",
                last_seen=now,
            ),
            Ownership(
                participant_id=reactionman.id,
                game_id=new_game.id,
                platform=Platform.steam,
                owned_since=now - timedelta(days=2),
                owned_since_source="store_entitlement",
                last_seen=now,
            ),
            Ownership(
                participant_id=lob.id,
                game_id=detected_game.id,
                platform=Platform.steam,
                first_seen_at=now - timedelta(days=1),
                first_seen_is_baseline=False,
                last_seen=now,
            ),
            Ownership(
                participant_id=lob.id,
                game_id=import_only.id,
                platform=Platform.steam,
                owned_since=now - timedelta(days=1),
                owned_since_source=None,
                first_seen_at=now - timedelta(days=1),
                first_seen_is_baseline=True,
                last_seen=now,
            ),
            Ownership(
                participant_id=lob.id,
                game_id=tool.id,
                platform=Platform.steam,
                owned_since=now - timedelta(days=1),
                owned_since_source="store_entitlement",
                last_seen=now,
            ),
        ]
    )
    db.commit()

    result = recent_acquisitions(days=30, db=db)

    assert [item["game"].title for item in result] == ["Newly Detected", "Fresh Game"]
    assert result[0]["date_kind"] == "first_seen"
    assert result[1]["date_kind"] == "acquired"
    assert result[1]["participant"].nickname == "PlayerTwo"
    assert result[1]["platforms"] == [Platform.steam]
