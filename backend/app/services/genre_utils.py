from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

UUID_PATTERN = re.compile(r"\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b", re.IGNORECASE)
OBJECT_FIELD_PATTERN = re.compile(r"['\"]?[A-Za-z_][A-Za-z0-9_ ]*['\"]?\s*:")


def sanitize_genres(values: Iterable[Any] | None) -> list[str]:
    genres: dict[str, str] = {}
    for value in values or []:
        genre = str(value).strip()
        if not is_plausible_genre(genre):
            continue
        genres.setdefault(genre.casefold(), genre)
    return sorted(genres.values(), key=str.casefold)


def is_plausible_genre(value: str) -> bool:
    if not value or len(value) > 80:
        return False
    if any(character in value for character in "{}[]"):
        return False
    if OBJECT_FIELD_PATTERN.search(value) or UUID_PATTERN.search(value):
        return False
    if value.casefold() in {"true", "false", "none", "null", "nan"}:
        return False
    return any(character.isalpha() for character in value)
