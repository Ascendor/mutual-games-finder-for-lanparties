from app.api.ownerships import participant_games
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
