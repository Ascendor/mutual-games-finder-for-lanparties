import json
import secrets
import time
from html import escape
from threading import Lock
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models import Account, Participant
from app.schemas import AccountRead, SteamConnectionRead, SteamProfileRead
from app.services import provider_auth
from app.services.account_identity import apply_account_identity
from app.services.steam_auth import (
    build_steam_login_url,
    resolve_steam_profile,
    upsert_steam_account,
    verify_steam_openid,
)

router = APIRouter()
STEAM_LOGIN_TTL_SECONDS = 10 * 60
_steam_login_lock = Lock()
_pending_steam_logins: dict[str, tuple[int, float, str]] = {}


class ProviderCodePayload(BaseModel):
    code: str = ""
    email: str | None = None
    password: str | None = None
    two_factor_code: str | None = None


class SteamProfilePayload(BaseModel):
    profile: str


class SteamConnectPayload(SteamProfilePayload):
    participant_id: int


class SteamLoginStartPayload(BaseModel):
    participant_id: int
    origin: str


def _get_account(db: Session, account_id: int) -> Account:
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(404, "account not found")
    return account


def _allowed_origin(origin: str) -> str:
    value = origin.rstrip("/")
    parsed = urlparse(value)
    configured = {item.rstrip("/") for item in settings.cors_origin_list}
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or value not in configured
    ):
        raise HTTPException(400, "Ungültige Rückkehradresse für die Steam-Anmeldung.")
    return value


def _steam_callback_html(payload: dict, target_origin: str) -> HTMLResponse:
    event_json = json.dumps(payload, ensure_ascii=True).replace("<", "\\u003c")
    origin_json = json.dumps(target_origin)
    success = bool(payload.get("success"))
    heading = "Steam ist verbunden" if success else "Steam-Verbindung fehlgeschlagen"
    message = escape(str(payload.get("message") or ""))
    body = f"""<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{heading}</title>
  <style>
    body {{ font: 16px system-ui, sans-serif; margin: 3rem auto; max-width: 34rem; padding: 0 1rem; }}
    h1 {{ font-size: 1.5rem; }}
  </style>
</head>
<body>
  <h1>{heading}</h1>
  <p>{message}</p>
  <p>Dieses Fenster kann geschlossen werden.</p>
  <script>
    if (window.opener) {{
      window.opener.postMessage({event_json}, {origin_json});
      window.close();
    }}
  </script>
</body>
</html>"""
    return HTMLResponse(body)


@router.get("/status")
def auth_status(db: Session = Depends(get_db)):
    return provider_auth.status(db)


@router.post("/steam/resolve", response_model=SteamProfileRead)
def resolve_steam(payload: SteamProfilePayload):
    try:
        return resolve_steam_profile(payload.profile).to_dict()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Steam ist gerade nicht erreichbar: {exc}") from exc


@router.post("/steam/connect", response_model=SteamConnectionRead)
def connect_steam(payload: SteamConnectPayload, db: Session = Depends(get_db)):
    if not db.get(Participant, payload.participant_id):
        raise HTTPException(404, "participant not found")
    try:
        profile = resolve_steam_profile(payload.profile)
        if not profile.library_accessible:
            raise ValueError(
                "Die Steam-Spielebibliothek ist nicht öffentlich. "
                "Setze die Spieldetails bei Steam auf Öffentlich und prüfe das Profil erneut."
            )
        account = upsert_steam_account(db, payload.participant_id, profile)
        return {**profile.to_dict(), "account": account}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Steam ist gerade nicht erreichbar: {exc}") from exc


@router.post("/steam/start")
def start_steam_login(payload: SteamLoginStartPayload, db: Session = Depends(get_db)):
    if not db.get(Participant, payload.participant_id):
        raise HTTPException(404, "participant not found")
    origin = _allowed_origin(payload.origin)
    now = time.monotonic()
    state = secrets.token_urlsafe(24)
    with _steam_login_lock:
        expired = [key for key, (_, expires_at, _) in _pending_steam_logins.items() if expires_at <= now]
        for key in expired:
            _pending_steam_logins.pop(key, None)
        _pending_steam_logins[state] = (
            payload.participant_id,
            now + STEAM_LOGIN_TTL_SECONDS,
            origin,
        )
    return {
        "login_url": build_steam_login_url(
            f"{origin}/api/provider-auth/steam/callback?state={state}",
            f"{origin}/",
        ),
        "state": state,
        "expires_in": STEAM_LOGIN_TTL_SECONDS,
    }


@router.get("/steam/callback", response_class=HTMLResponse)
def steam_login_callback(request: Request, state: str, db: Session = Depends(get_db)):
    with _steam_login_lock:
        pending = _pending_steam_logins.pop(state, None)
    if not pending or pending[1] <= time.monotonic():
        return _steam_callback_html(
            {
                "type": "steam-login-result",
                "state": state,
                "success": False,
                "message": "Die Steam-Anmeldung ist abgelaufen. Starte sie bitte erneut.",
            },
            pending[2] if pending else "*",
        )

    participant_id, _, origin = pending
    try:
        steam_id = verify_steam_openid(dict(request.query_params))
        profile = resolve_steam_profile(steam_id)
        account = (
            upsert_steam_account(db, participant_id, profile)
            if profile.library_accessible
            else None
        )
        message = (
            f"{profile.display_name} wurde erkannt. Die Bibliothek enthält {profile.game_count} Spiele."
            if account
            else (
                f"{profile.display_name} wurde erkannt, aber die Spielebibliothek ist nicht öffentlich. "
                "Setze bei Steam unter Privatsphäre die Spieldetails auf Öffentlich."
            )
        )
        account_payload = (
            AccountRead.model_validate(account).model_dump(mode="json")
            if account
            else None
        )
        return _steam_callback_html(
            {
                "type": "steam-login-result",
                "state": state,
                "success": True,
                "message": message,
                "account": account_payload,
                "profile": profile.to_dict(),
            },
            origin,
        )
    except Exception as exc:
        return _steam_callback_html(
            {
                "type": "steam-login-result",
                "state": state,
                "success": False,
                "message": str(exc),
            },
            origin,
        )


@router.get("/accounts/{account_id}/status")
def account_auth_status(account_id: int, db: Session = Depends(get_db)):
    account = _get_account(db, account_id)
    try:
        return provider_auth.account_status(account)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/accounts/{account_id}/start")
def start_login(account_id: int, db: Session = Depends(get_db)):
    account = _get_account(db, account_id)
    try:
        return provider_auth.start(account)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/accounts/{account_id}/complete")
def complete_login(account_id: int, payload: ProviderCodePayload, db: Session = Depends(get_db)):
    account = _get_account(db, account_id)
    try:
        result = provider_auth.complete(account, payload.code.strip(), payload.model_dump(exclude_none=True))
        if result.get("authenticated"):
            apply_account_identity(account, result, participant_fallback=True)
            db.commit()
        return result
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/accounts/{account_id}/poll")
def poll_login(account_id: int, db: Session = Depends(get_db)):
    account = _get_account(db, account_id)
    try:
        result = provider_auth.poll(account)
        if result.get("authenticated"):
            if result.get("xuid"):
                account.account_id = str(result["xuid"])
            if result.get("gamertag"):
                account.display_name = str(result["gamertag"])
            db.commit()
        return result
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/accounts/{account_id}/logout")
def logout(account_id: int, db: Session = Depends(get_db)):
    account = _get_account(db, account_id)
    try:
        return provider_auth.logout(account)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc


