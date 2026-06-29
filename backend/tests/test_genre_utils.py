from app.services.genre_utils import sanitize_genres


def test_sanitize_genres_removes_serialized_playnite_fragments():
    assert sanitize_genres(
        [
            "'Sources': ['000001db-dbd1-46c6-b5d0-b1ba559d10e4']}",
            "'Visible': True",
            "'Width': 'NaN'}",
            "{'Field': 41",
            "{'Import': True",
            "Action",
            "Role-playing (RPG)",
            "action",
        ]
    ) == ["Action", "Role-playing (RPG)"]
