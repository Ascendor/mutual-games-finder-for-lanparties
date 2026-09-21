from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from urllib.parse import unquote, urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Account, Platform

@dataclass(frozen=True)
class SteamProfile:
    steam_id: str
    display_name: str
    profile_url: str
    avatar_url: str | None
    library_accessible: bool
    game_count: int | None

    def to_dict(self) -> dict[str, str | int | bool | None]:
        return asdict(self)

def resolve_steam_profile(reference: str) -> SteamProfile:
    steam_id = _steam_id_from_reference(reference)
    if not steam_id:
        vanity = _steam_vanity_from_reference(reference)
        if not vanity:
            raise ValueError(
                "Steam-Profil nicht erkannt. Verwende den Profilnamen, den vollständigen Profillink "
                "oder eine 17-stellige SteamID64."
            )
        steam_id = _resolve_vanity_name(vanity)

    player = _load_player_summary(steam_id)
    accessible, game_count = _load_library_status(steam_id)
    return SteamProfile(
        steam_id=steam_id,
        display_name=str(player.get("personaname") or steam_id),
        profile_url=str(player.get("profileurl") or f"https://steamcommunity.com/profiles/{steam_id}/"),
        avatar_url=player.get("avatarfull") or player.get("avatarmedium"),
        library_accessible=accessible,
        game_count=game_count,
    )


def upsert_steam_account(db: Session, participant_id: int, profile: SteamProfile) -> Account:
    linked = db.scalar(
        select(Account).where(
            Account.platform == Platform.steam,
            Account.account_id == profile.steam_id,
        )
    )
    if linked and linked.participant_id != participant_id:
        raise ValueError("Dieses Steam-Konto ist bereits mit einem anderen Teilnehmer verbunden.")

    account = db.scalar(
        select(Account).where(
            Account.participant_id == participant_id,
            Account.platform == Platform.steam,
        )
    )
    if account:
        account.account_id = profile.steam_id
        account.display_name = profile.display_name
        account.last_error = None
    else:
        account = Account(
            participant_id=participant_id,
            platform=Platform.steam,
            account_id=profile.steam_id,
            display_name=profile.display_name,
        )
        db.add(account)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("Dieses Steam-Konto ist bereits mit einem anderen Teilnehmer verbunden.") from exc
    db.refresh(account)
    return account


def _steam_api_key() -> str:
    if not settings.steam_api_key:
        raise ValueError("Der Steam-API-Schlüssel ist auf dem Server nicht konfiguriert.")
    return settings.steam_api_key


def _clean_reference(reference: str) -> str:
    value = reference.strip().lstrip("\ufeff")
    for _ in range(2):
        if len(value) >= 2 and value[0] in "\"'“”‘’" and value[-1] in "\"'“”‘’":
            value = value[1:-1].strip()
    return value


def _steam_id_from_reference(reference: str) -> str | None:
    value = _clean_reference(reference)
    if re.fullmatch(r"\d{17}", value):
        return value
    match = re.search(
        r"(?:steamcommunity\.com/)?(?:profiles|openid/id)/(\d{17})(?:[/?#]|$)",
        value,
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else None


def _steam_vanity_from_reference(reference: str) -> str | None:
    value = _clean_reference(reference)
    candidate = value
    if "steamcommunity.com" in value.casefold():
        parsed = urlparse(value if "://" in value else f"https://{value}")
        match = re.search(r"(?:^|/)id/([^/?#]+)", parsed.path, flags=re.IGNORECASE)
        if not match:
            return None
        candidate = unquote(match.group(1))
    candidate = candidate.strip().strip("/")
    return candidate if re.fullmatch(r"[A-Za-z0-9_-]{2,64}", candidate) else None


def _resolve_vanity_name(vanity: str) -> str:
    response = httpx.get(
        "https://api.steampowered.com/ISteamUser/ResolveVanityURL/v0001/",
        params={"key": _steam_api_key(), "vanityurl": vanity},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json().get("response", {})
    steam_id = str(payload.get("steamid") or "")
    if payload.get("success") != 1 or not re.fullmatch(r"\d{17}", steam_id):
        raise ValueError("Unter diesem Namen wurde kein Steam-Profil gefunden.")
    return steam_id


def _load_player_summary(steam_id: str) -> dict:
    response = httpx.get(
        "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/",
        params={"key": _steam_api_key(), "steamids": steam_id},
        timeout=15,
    )
    response.raise_for_status()
    players = response.json().get("response", {}).get("players") or []
    if not players:
        raise ValueError("Das Steam-Profil konnte nicht geladen werden.")
    return players[0]


def _load_library_status(steam_id: str) -> tuple[bool, int | None]:
    response = httpx.get(
        "https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/",
        params={
            "key": _steam_api_key(),
            "steamid": steam_id,
            "include_appinfo": 0,
            "include_played_free_games": 1,
            "format": "json",
        },
        timeout=20,
    )
    response.raise_for_status()
    library = response.json().get("response")
    if not isinstance(library, dict) or "game_count" not in library:
        return False, None
    return True, int(library.get("game_count") or 0)
