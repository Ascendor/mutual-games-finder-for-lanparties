from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings
from app.services.credential_storage import write_private_json


def steam_credentials_path(account_id: int) -> Path:
    return Path(settings.provider_auth_root) / "steam" / str(account_id) / "auth.json"


def save_steam_credentials(account_id: int, steam_id: str, refresh_token: str) -> None:
    path = steam_credentials_path(account_id)
    write_private_json(path, {"steam_id": steam_id, "refresh_token": refresh_token})


def load_steam_credentials(account_id: int) -> dict[str, str] | None:
    path = steam_credentials_path(account_id)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    steam_id = str(payload.get("steam_id") or "").strip()
    refresh_token = str(payload.get("refresh_token") or "").strip()
    if not steam_id or not refresh_token:
        return None
    return {"steam_id": steam_id, "refresh_token": refresh_token}


def delete_steam_credentials(account_id: int) -> None:
    path = steam_credentials_path(account_id)
    path.unlink(missing_ok=True)
    try:
        path.parent.rmdir()
    except OSError:
        pass


def load_authenticated_steam_library(account_id: int, steam_id: str) -> list[dict[str, Any]] | None:
    credentials = load_steam_credentials(account_id)
    if not credentials:
        return None
    if credentials["steam_id"] != steam_id:
        raise RuntimeError("Die gespeicherte Steam-Anmeldung gehört zu einer anderen SteamID. Bitte neu verbinden.")
    response = httpx.post(
        f"{settings.steam_helper_url.rstrip('/')}/libraries",
        json={
            "steam_id": steam_id,
            "refresh_token": credentials["refresh_token"],
        },
        timeout=max(135.0, settings.steam_helper_timeout_seconds + 15.0),
    )
    if response.status_code in {401, 403}:
        raise RuntimeError("Die Steam-Anmeldung ist abgelaufen. Bitte Steam neu verbinden.")
    response.raise_for_status()
    payload = response.json()
    games = payload.get("games") if isinstance(payload, dict) else None
    if not isinstance(games, list):
        raise RuntimeError("Steam hat keine verwertbare Spielebibliothek geliefert.")
    return [item for item in games if isinstance(item, dict)]
