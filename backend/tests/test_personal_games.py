from app.api.ownerships import participant_games
from app.models import Account, Game, Ownership, Participant, Platform


def test_participant_games_groups_platforms_and_searches(db):
    participant = Participant(nickname="PlayerOne")
    other = Participant(nickname="PlayerTwo")
    portal = Game(title="Portal", normalized_title="portal", singleplayer=True)
    quake = Game(title="Quake", normalized_title="quake", multiplayer=True)
    db.add_all([participant, other, portal, quake])
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
                participant_id=other.id,
                game_id=quake.id,
                platform=Platform.steam,
            ),
        ]
    )
    db.commit()

    result = participant_games(participant.id, "portal", 1, 25, "title", False, db)

    assert result["total"] == 1
    assert result["items"][0]["game"].id == portal.id
    assert result["items"][0]["total_playtime_minutes"] == 105
    assert [item["platform"] for item in result["items"][0]["platforms"]] == [
        Platform.gog,
        Platform.steam,
    ]
    assert result["items"][0]["platforms"][1]["account_display_name"] == "PlayerOne on Steam"
