from app.models import Account, Game, Ownership, Participant, Platform
from app.services.normalization import normalize_title
from app.services.recommendations import find_best_lan_games, find_common_coop_games, find_common_games, find_common_lan_games, find_games_for_group_size, find_most_popular_games, find_new_for_group_games


def add_owned(db, participant, game, minutes=0):
    account = Account(participant_id=participant.id, platform=Platform.steam, account_id=f"{participant.nickname}-{game.title}")
    db.add(account)
    db.flush()
    db.add(
        Ownership(
            participant_id=participant.id,
            account_id=account.id,
            game_id=game.id,
            platform=Platform.steam,
            playtime_minutes=minutes,
        )
    )


def test_common_and_coop_recommendations(db):
    ada = Participant(nickname="Ada", present=True)
    linus = Participant(nickname="Linus", present=True)
    coop = Game(
        title="Deep Rock Galactic",
        normalized_title=normalize_title("Deep Rock Galactic"),
        multiplayer=True,
        online_coop=True,
        lan=True,
        min_players=1,
        max_players=4,
    )
    solo = Game(title="Solo Quest", normalized_title=normalize_title("Solo Quest"), singleplayer=True)
    db.add_all([ada, linus, coop, solo])
    db.flush()
    add_owned(db, ada, coop, 100)
    add_owned(db, linus, coop, 50)
    add_owned(db, ada, solo, 20)
    db.commit()

    common = find_common_games(db, [ada.id, linus.id])
    coop_games = find_common_coop_games(db, [ada.id, linus.id])
    sized = find_games_for_group_size(db, 4)

    assert [item.game.title for item in common] == ["Deep Rock Galactic"]
    assert [item.game.title for item in coop_games] == ["Deep Rock Galactic"]
    assert [item.game.title for item in sized] == ["Deep Rock Galactic"]


def test_known_free_steam_game_is_available_to_every_selected_player(db):
    owner = Participant(nickname="Owner", present=True)
    ada = Participant(nickname="Ada", present=True)
    linus = Participant(nickname="Linus", present=True)
    free_game = Game(
        title="Free Arena",
        normalized_title=normalize_title("Free Arena"),
        is_free=True,
        multiplayer=True,
    )
    paid_game = Game(
        title="Paid Arena",
        normalized_title=normalize_title("Paid Arena"),
        multiplayer=True,
    )
    db.add_all([owner, ada, linus, free_game, paid_game])
    db.flush()
    add_owned(db, owner, free_game, 120)
    add_owned(db, owner, paid_game, 120)
    db.commit()

    common = find_common_games(db, [ada.id, linus.id])

    assert [item.game.title for item in common] == ["Free Arena"]
    assert common[0].owner_count == 0
    assert common[0].platforms == [Platform.steam]



def test_recommendation_views_have_distinct_filters(db):
    ada = Participant(nickname="Ada", present=True)
    linus = Participant(nickname="Linus", present=True)
    lan_game = Game(title="LAN Arena", normalized_title=normalize_title("LAN Arena"), multiplayer=True, lan=True, min_players=2, max_players=8)
    coop_game = Game(title="Coop Cave", normalized_title=normalize_title("Coop Cave"), multiplayer=True, online_coop=True, min_players=1, max_players=4)
    popular_solo = Game(title="Popular Solo", normalized_title=normalize_title("Popular Solo"), singleplayer=True, min_players=1, max_players=1)
    db.add_all([ada, linus, lan_game, coop_game, popular_solo])
    db.flush()
    add_owned(db, ada, lan_game, 10)
    add_owned(db, linus, lan_game, 20)
    add_owned(db, ada, coop_game, 500)
    add_owned(db, linus, coop_game, 100)
    add_owned(db, ada, popular_solo, 1000)
    db.commit()

    assert [item.game.title for item in find_common_coop_games(db, [ada.id, linus.id])] == ["Coop Cave"]
    assert [item.game.title for item in find_common_lan_games(db, [ada.id, linus.id])] == ["LAN Arena"]
    assert [item.game.title for item in find_best_lan_games(db)] == ["LAN Arena"]
    assert "Popular Solo" in [item.game.title for item in find_most_popular_games(db)]


def test_common_coop_does_not_hide_games_because_store_has_no_reliable_capacity(db):
    players = [Participant(nickname=f"Player {index}", present=True) for index in range(5)]
    game = Game(
        title="Unknown Coop Capacity",
        normalized_title=normalize_title("Unknown Coop Capacity"),
        multiplayer=True,
        online_coop=True,
        min_players=1,
        max_players=1,
    )
    db.add_all([*players, game])
    db.flush()
    for player in players:
        add_owned(db, player, game)
    db.commit()

    assert [item.game.title for item in find_common_coop_games(db, [player.id for player in players])] == [
        "Unknown Coop Capacity"
    ]


def test_group_size_excludes_games_with_known_insufficient_capacity(db):
    players = [Participant(nickname=f"Known {index}", present=True) for index in range(5)]
    game = Game(
        title="Four Player Coop",
        normalized_title=normalize_title("Four Player Coop"),
        multiplayer=True,
        online_coop=True,
        min_players=1,
        max_players=4,
        player_count_known=True,
    )
    db.add_all([*players, game])
    db.flush()
    for player in players:
        add_owned(db, player, game)
    db.commit()

    assert find_games_for_group_size(db, 5) == []


def test_new_for_group_prefers_broadly_owned_low_playtime_games(db):
    ada = Participant(nickname="Ada", present=True)
    linus = Participant(nickname="Linus", present=True)
    grace = Participant(nickname="Grace", present=True)
    fresh = Game(title="Fresh Coop", normalized_title=normalize_title("Fresh Coop"), multiplayer=True, min_players=1, max_players=4)
    exhausted = Game(title="Exhausted Classic", normalized_title=normalize_title("Exhausted Classic"), multiplayer=True, min_players=1, max_players=4)
    db.add_all([ada, linus, grace, fresh, exhausted])
    db.flush()
    for participant in (ada, linus, grace):
        add_owned(db, participant, fresh, 5)
        add_owned(db, participant, exhausted, 5000)
    db.commit()

    assert [item.game.title for item in find_new_for_group_games(db)][:2] == ["Fresh Coop", "Exhausted Classic"]
