from app.services.normalization import normalize_title


def test_normalizes_platform_title_variants():
    assert normalize_title("Left 4 Dead 2") == normalize_title("Left 4 Dead(TM) 2")
    assert normalize_title("LEFT 4 DEAD 2") == "left 4 dead 2"

