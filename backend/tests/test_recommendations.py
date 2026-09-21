from app.models import Account, Game, Ownership, Participant, Platform
from datetime import datetime

from app.models import PlatformGameMapping
from app.services.normalization import normalize_title
from app.services.recommendations import find_best_lan_games, find_common_coop_games, find_common_games, find_common_lan_games, find_games_for_group_size, find_most_popular_games, find_new_for_group_games


def add_owned(db, participant, game, minutes=0):
    account = Account(
        participant_id=participant.id,
        platform=Platform.steam,
        account_id=f"{participant.nickname}-{game.title}",
        last_successful_sync=datetime.utcnow(),
    )
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


def test_non_games_are_excluded_from_recommendations(db):
    participant = Participant(nickname="Viewer", present=True)
    software = Game(
        title="VR Video Player",
        normalized_title=normalize_title("VR Video Player"),
        is_game=False,
        non_game_reason="Software-Genre: utilities",
    )
    db.add_all([participant, software])
    db.flush()
    add_owned(db, participant, software, 120)
    db.commit()

    assert find_common_games(db, [participant.id]) == []
    assert find_most_popular_games(db) == []


def test_known_free_steam_game_is_available_to_every_selected_player(db):
    ada = Participant(nickname="Ada", present=True)
    linus = Participant(nickname="Linus", present=True)
    free_game = Game(
        title="Free Arena",
        normalized_title=normalize_title("Free Arena"),
        is_free=True,
        multiplayer=True,
    )
    db.add_all([ada, linus, free_game])
    db.flush()
    add_owned(db, ada, free_game, 120)
    db.commit()

    common = find_common_games(db, [ada.id, linus.id])

    assert [item.game.title for item in common] == ["Free Arena"]
    assert common[0].owner_count == 1
    assert common[0].available_player_count == 2
    assert common[0].known_player_count == 2
    assert common[0].coverage_percent == 100
    assert common[0].platforms == [Platform.steam]


def test_free_game_owned_only_outside_selected_group_is_not_recommended(db):
    outsider = Participant(nickname="Outsider", present=False)
    ada = Participant(nickname="Ada", present=True)
    linus = Participant(nickname="Linus", present=True)
    free_game = Game(
        title="Unknown Free Arena",
        normalized_title=normalize_title("Unknown Free Arena"),
        is_free=True,
        multiplayer=True,
    )
    db.add_all([outsider, ada, linus, free_game])
    db.flush()
    add_owned(db, outsider, free_game, 120)
    db.commit()

    assert find_common_games(db, [ada.id, linus.id]) == []


def test_free_games_with_broader_library_adoption_rank_higher(db):
    players = [
        Participant(nickname="Ada", present=True),
        Participant(nickname="Linus", present=True),
        Participant(nickname="Grace", present=True),
    ]
    widely_owned = Game(
        title="Widely Owned Free Game",
        normalized_title=normalize_title("Widely Owned Free Game"),
        is_free=True,
        multiplayer=True,
    )
    barely_owned = Game(
        title="Barely Owned Free Game",
        normalized_title=normalize_title("Barely Owned Free Game"),
        is_free=True,
        multiplayer=True,
    )
    db.add_all([*players, widely_owned, barely_owned])
    db.flush()
    add_owned(db, players[0], widely_owned, 10)
    add_owned(db, players[1], widely_owned, 10)
    add_owned(db, players[0], barely_owned, 10_000)
    db.commit()

    recommendations = find_common_games(db, [player.id for player in players])

    assert [item.game.title for item in recommendations] == [
        "Widely Owned Free Game",
        "Barely Owned Free Game",
    ]
    assert recommendations[0].owner_count == 2
    assert recommendations[0].available_player_count == 3


def test_common_games_rank_full_ownership_then_free_then_partial(db):
    players = [
        Participant(nickname="Ada", present=True),
        Participant(nickname="Linus", present=True),
        Participant(nickname="Grace", present=True),
    ]
    fully_owned = Game(
        title="Fully Owned",
        normalized_title=normalize_title("Fully Owned"),
        multiplayer=True,
    )
    broadly_owned_free = Game(
        title="Broad Free",
        normalized_title=normalize_title("Broad Free"),
        is_free=True,
        multiplayer=True,
    )
    barely_owned_free = Game(
        title="Barely Free",
        normalized_title=normalize_title("Barely Free"),
        is_free=True,
        multiplayer=True,
    )
    partially_owned = Game(
        title="Partial Paid",
        normalized_title=normalize_title("Partial Paid"),
        multiplayer=True,
    )
    db.add_all(
        [
            *players,
            fully_owned,
            broadly_owned_free,
            barely_owned_free,
            partially_owned,
        ]
    )
    db.flush()
    for player in players:
        add_owned(db, player, fully_owned)
    for player in players[:2]:
        add_owned(db, player, broadly_owned_free)
        add_owned(db, player, partially_owned)
    add_owned(db, players[0], barely_owned_free)
    db.commit()

    recommendations = find_common_games(
        db,
        [player.id for player in players],
        minimum_coverage=0,
    )

    assert [item.game.title for item in recommendations] == [
        "Fully Owned",
        "Broad Free",
        "Barely Free",
        "Partial Paid",
    ]


def test_free_games_can_be_counted_only_for_actual_owners(db):
    players = [
        Participant(nickname="Ada", present=True),
        Participant(nickname="Linus", present=True),
        Participant(nickname="Grace", present=True),
    ]
    anchor = Game(
        title="Anchor",
        normalized_title=normalize_title("Anchor"),
        multiplayer=True,
    )
    free_game = Game(
        title="Free Arena",
        normalized_title=normalize_title("Free Arena"),
        is_free=True,
        multiplayer=True,
    )
    db.add_all([*players, anchor, free_game])
    db.flush()
    for player in players:
        add_owned(db, player, anchor)
    add_owned(db, players[0], free_game)
    db.commit()

    counted_for_all = find_common_games(
        db,
        [player.id for player in players],
        minimum_coverage=0.75,
        free_games_as_owned=True,
    )
    actual_owners_only = find_common_games(
        db,
        [player.id for player in players],
        minimum_coverage=0.75,
        free_games_as_owned=False,
    )

    assert "Free Arena" in [item.game.title for item in counted_for_all]
    assert "Free Arena" not in [item.game.title for item in actual_owners_only]


def test_common_games_ignore_unreadable_library_and_apply_coverage_threshold(db):
    ada = Participant(nickname="Ada", present=True)
    linus = Participant(nickname="Linus", present=True)
    player_three = Participant(nickname="PlayerThree", present=True)
    broad = Game(
        title="Broadly Owned",
        normalized_title=normalize_title("Broadly Owned"),
        multiplayer=True,
    )
    partial = Game(
        title="Half Owned",
        normalized_title=normalize_title("Half Owned"),
        multiplayer=True,
    )
    db.add_all([ada, linus, player_three, broad, partial])
    db.flush()
    add_owned(db, ada, broad)
    add_owned(db, linus, broad)
    add_owned(db, ada, partial)
    db.add(
        Account(
            participant_id=player_three.id,
            platform=Platform.steam,
            account_id="private-library",
            last_error="Steam library is not accessible",
        )
    )
    db.commit()

    at_75_percent = find_common_games(
        db,
        [ada.id, linus.id, player_three.id],
        minimum_coverage=0.75,
    )
    at_50_percent = find_common_games(
        db,
        [ada.id, linus.id, player_three.id],
        minimum_coverage=0.5,
    )

    assert [item.game.title for item in at_75_percent] == ["Broadly Owned"]
    assert [item.game.title for item in at_50_percent] == [
        "Broadly Owned",
        "Half Owned",
    ]
    assert at_75_percent[0].available_player_count == 2
    assert at_75_percent[0].known_player_count == 2
    assert at_75_percent[0].coverage_percent == 100
    assert [player.nickname for player in at_75_percent[0].unknown_players] == [
        "PlayerThree"
    ]
    assert at_50_percent[1].coverage_percent == 50


def test_unsynced_playnite_only_account_does_not_make_game_unknown(db):
    owner = Participant(nickname="Owner", present=True)
    mixed = Participant(nickname="Mixed", present=True)
    game = Game(
        title="Steam Game",
        normalized_title=normalize_title("Steam Game"),
        multiplayer=True,
    )
    db.add_all([owner, mixed, game])
    db.flush()
    add_owned(db, owner, game)
    db.add_all(
        [
            PlatformGameMapping(
                game_id=game.id,
                platform=Platform.ea,
                platform_game_id="ea-steam-game",
                platform_title="Steam Game",
                normalized_title=normalize_title("Steam Game"),
            ),
            Account(
                participant_id=mixed.id,
                platform=Platform.steam,
                account_id="mixed-steam",
                last_successful_sync=datetime.utcnow(),
            ),
            Account(
                participant_id=mixed.id,
                platform=Platform.ea,
                account_id="mixed-ea",
            ),
        ]
    )
    db.commit()

    recommendations = find_common_games(
        db,
        [owner.id, mixed.id],
        minimum_coverage=0.5,
    )

    assert [item.game.title for item in recommendations] == ["Steam Game"]
    assert recommendations[0].known_player_count == 2
    assert recommendations[0].coverage_percent == 50
    assert recommendations[0].unknown_players == []



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
    fresh_broad = Game(title="Fresh Broad", normalized_title=normalize_title("Fresh Broad"), multiplayer=True, min_players=1, max_players=4)
    fresh_narrow = Game(title="Fresh Narrow", normalized_title=normalize_title("Fresh Narrow"), multiplayer=True, min_players=1, max_players=4)
    fresh_high_average = Game(title="Fresh High Average", normalized_title=normalize_title("Fresh High Average"), multiplayer=True, min_players=1, max_players=4)
    exhausted = Game(title="Exhausted Classic", normalized_title=normalize_title("Exhausted Classic"), multiplayer=True, min_players=1, max_players=4)
    db.add_all([ada, linus, grace, fresh_broad, fresh_narrow, fresh_high_average, exhausted])
    db.flush()
    for participant in (ada, linus, grace):
        add_owned(db, participant, fresh_broad, 0)
        add_owned(db, participant, exhausted, 5000)
    add_owned(db, ada, fresh_narrow, 0)
    add_owned(db, linus, fresh_narrow, 0)
    add_owned(db, ada, fresh_high_average, 0)
    add_owned(db, linus, fresh_high_average, 0)
    add_owned(db, grace, fresh_high_average, 600)
    db.commit()

    assert [item.game.title for item in find_new_for_group_games(db)][:4] == [
        "Fresh Broad",
        "Fresh Narrow",
        "Fresh High Average",
        "Exhausted Classic",
    ]
