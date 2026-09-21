from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Account, Platform, SyncRun
from app.services.import_providers import ImportedGame
from app.services.steam_auth import SteamProfile, resolve_steam_profile, upsert_steam_account
from app.services.steam_client_credentials import save_steam_credentials
from app.services.sync_service import resolve_game, upsert_ownership


def start_steam_qr_login() -> dict[str, Any]:
    response = httpx.post(
        f"{settings.steam_helper_url.rstrip('/')}/sessions",
        timeout=settings.steam_helper_timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("state") or not payload.get("qr_data_url"):
        raise RuntimeError("Steam-Hilfsdienst hat keinen QR-Code geliefert.")
    return payload


def poll_steam_qr_login(state: str) -> dict[str, Any]:
    response = httpx.get(
        f"{settings.steam_helper_url.rstrip('/')}/sessions/{state}",
        timeout=settings.steam_helper_timeout_seconds,
    )
    if response.status_code == 404:
        return {"status": "failed", "message": "Die Steam-Anmeldung ist abgelaufen."}
    response.raise_for_status()
    return response.json()


def complete_steam_qr_login(
    db: Session,
    participant_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    steam_id = str(payload.get("steam_id") or "").strip()
    if not steam_id.isdigit() or len(steam_id) != 17:
        raise ValueError("Steam hat keine gültige SteamID geliefert.")

    raw_games = payload.get("games")
    if not isinstance(raw_games, list):
        raise ValueError("Steam hat keine verwertbare Spielebibliothek geliefert.")
    refresh_token = str(payload.get("refresh_token") or "").strip()
    if not refresh_token:
        raise ValueError("Steam hat kein erneuerbares Anmeldetoken geliefert.")
    try:
        profile = resolve_steam_profile(steam_id)
        profile = replace(profile, library_accessible=True, game_count=len(raw_games))
    except Exception:
        display_name = str(payload.get("account_name") or steam_id).strip()
        profile = SteamProfile(
            steam_id=steam_id,
            display_name=display_name,
            profile_url=f"https://steamcommunity.com/profiles/{steam_id}/",
            avatar_url=None,
            library_accessible=True,
            game_count=len(raw_games),
        )

    account = upsert_steam_account(db, participant_id, profile)
    save_steam_credentials(account.id, steam_id, refresh_token)
    imported = 0
    dated = 0
    for item in raw_games:
        if not isinstance(item, dict):
            continue
        appid = str(item.get("appid") or "").strip()
        title = str(item.get("title") or "").strip()
        if not appid.isdigit() or not title:
            continue
        owned_since = _parse_iso_datetime(item.get("owned_since"))
        game_data = ImportedGame(
            platform_game_id=appid,
            title=title,
            owned_since=owned_since,
            owned_since_source="steam_license" if owned_since else None,
            feature_metadata_known=False,
            player_count_known=False,
        )
        game = resolve_game(db, Platform.steam, game_data)
        upsert_ownership(
            db,
            account,
            game,
            game_data,
            discovery_is_baseline=True,
        )
        imported += 1
        dated += int(owned_since is not None)

    account.last_successful_sync = datetime.utcnow()
    account.last_error = None
    db.add(
        SyncRun(
            account_id=account.id,
            finished_at=datetime.utcnow(),
            success=True,
            imported_games=imported,
            message=f"Steam QR login imported {imported} games; {dated} with license dates",
        )
    )
    db.commit()
    db.refresh(account)
    return {
        "status": "complete",
        "authenticated": True,
        "message": f"{imported} Steam-Spiele geladen.",
        "account": account,
        "profile": profile.to_dict(),
        "imported_games": imported,
        "dated_games": dated,
    }


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
