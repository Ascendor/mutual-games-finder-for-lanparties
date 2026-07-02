from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class GameClassification:
    is_game: bool | None
    reason: str | None = None


SOFTWARE_GENRES = {
    "accounting",
    "animation & modeling",
    "audio production",
    "design & illustration",
    "game development",
    "photo editing",
    "software training",
    "utilities",
    "video production",
    "web publishing",
}
NON_GAME_TITLE = re.compile(
    r"\b(?:demo|dedicated\s+server|test\s+server|sdk)\b",
    re.IGNORECASE,
)


def classify_game(
    title: str,
    genres: Iterable[str] = (),
    *,
    store_type: str | None = None,
) -> GameClassification:
    normalized_type = str(store_type or "").strip().casefold()
    if normalized_type and normalized_type != "game":
        return GameClassification(False, f"Store-Typ: {normalized_type}")

    if NON_GAME_TITLE.search(title):
        return GameClassification(False, "Eindeutiger Nicht-Spiel-Titel")

    normalized_genres = {
        str(genre).strip().casefold()
        for genre in genres
        if str(genre).strip()
    }
    software_genres = sorted(normalized_genres & SOFTWARE_GENRES)
    if software_genres:
        return GameClassification(
            False,
            "Software-Genre: " + ", ".join(software_genres),
        )

    return GameClassification(None)
