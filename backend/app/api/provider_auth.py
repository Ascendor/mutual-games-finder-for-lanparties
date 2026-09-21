import time
from dataclasses import dataclass
from secrets import token_urlsafe
from threading import Lock
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models import Account, Participant
from app.schemas import AccountRead, SteamConnectionRead, SteamProfileRead
from app.services import provider_auth
from app.services.account_identity import apply_account_identity
from app.services.steam_auth import (
    resolve_steam_profile,
    upsert_steam_account,
)
from app.services.steam_client_auth import complete_steam_qr_login, poll_steam_qr_login, start_steam_qr_login
from app.services.steam_client_credentials import delete_steam_credentials
from app.services.steam_openid import build_steam_openid_url, verify_steam_openid_response

router = APIRouter()
STEAM_LOGIN_TTL_SECONDS = 10 * 60
_steam_login_lock = Lock()
_pending_steam_logins: dict[str, tuple[int, float]] = {}
_steam_openid_lock = Lock()


@dataclass(frozen=True)
class PendingSteamOpenId:
    participant_id: int
    expires_at: float
    origin: str
    return_path: str
    callback_url: str


_pending_steam_openid: dict[str, PendingSteamOpenId] = {}


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


class SteamOpenIdStartPayload(BaseModel):
    participant_id: int
    origin: str
    return_path: str = "/logins"


def _get_account(db: Session, account_id: int) -> Account:
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(404, "account not found")
    return account


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
        delete_steam_credentials(account.id)
        return {**profile.to_dict(), "account": account}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Steam ist gerade nicht erreichbar: {exc}") from exc


@router.post("/steam/start")
def start_steam_login(payload: SteamLoginStartPayload, db: Session = Depends(get_db)):
    if not db.get(Participant, payload.participant_id):
        raise HTTPException(404, "participant not found")
    try:
        result = start_steam_qr_login()
    except Exception as exc:
        raise HTTPException(502, f"Steam-Anmeldung konnte nicht gestartet werden: {exc}") from exc
    state = str(result["state"])
    expires_in = int(result.get("expires_in") or STEAM_LOGIN_TTL_SECONDS)
    with _steam_login_lock:
        now = time.monotonic()
        expired = [key for key, (_, expires_at) in _pending_steam_logins.items() if expires_at <= now]
        for key in expired:
            _pending_steam_logins.pop(key, None)
        _pending_steam_logins[state] = (payload.participant_id, now + expires_in)
    return result


@router.get("/steam/poll/{state}")
def poll_steam_login(state: str, db: Session = Depends(get_db)):
    with _steam_login_lock:
        pending = _pending_steam_logins.get(state)
    if not pending or pending[1] <= time.monotonic():
        with _steam_login_lock:
            _pending_steam_logins.pop(state, None)
        raise HTTPException(404, "Die Steam-Anmeldung ist abgelaufen. Starte sie bitte erneut.")
    try:
        result = poll_steam_qr_login(state)
        if result.get("status") == "complete":
            result = complete_steam_qr_login(db, pending[0], result)
            result["account"] = AccountRead.model_validate(result["account"]).model_dump(mode="json")
            with _steam_login_lock:
                _pending_steam_logins.pop(state, None)
        elif result.get("status") == "failed":
            with _steam_login_lock:
                _pending_steam_logins.pop(state, None)
        return result
    except Exception as exc:
        raise HTTPException(502, f"Steam-Anmeldung konnte nicht abgeschlossen werden: {exc}") from exc


@router.get("/accounts/{account_id}/status")
def account_auth_status(account_id: int, db: Session = Depends(get_db)):
    account = _get_account(db, account_id)
    try:
        return provider_auth.account_status(account)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/steam/openid/start")
def start_steam_openid_login(
    payload: SteamOpenIdStartPayload,
    request: Request,
    db: Session = Depends(get_db),
):
    if not db.get(Participant, payload.participant_id):
        raise HTTPException(404, "participant not found")
    origin = _validated_frontend_origin(payload.origin, request)
    return_path = payload.return_path if payload.return_path in {"/logins", "/admin/logins"} else "/logins"
    state = token_urlsafe(32)
    callback_url = f"{origin}/api/provider-auth/steam/openid/callback?{urlencode({'state': state})}"
    pending = PendingSteamOpenId(
        participant_id=payload.participant_id,
        expires_at=time.monotonic() + STEAM_LOGIN_TTL_SECONDS,
        origin=origin,
        return_path=return_path,
        callback_url=callback_url,
    )
    with _steam_openid_lock:
        now = time.monotonic()
        expired = [key for key, item in _pending_steam_openid.items() if item.expires_at <= now]
        for key in expired:
            _pending_steam_openid.pop(key, None)
        _pending_steam_openid[state] = pending
    return {
        "login_url": build_steam_openid_url(callback_url, f"{origin}/"),
        "expires_in": STEAM_LOGIN_TTL_SECONDS,
    }


@router.get("/steam/openid/callback")
def complete_steam_openid_login(request: Request, state: str, db: Session = Depends(get_db)):
    with _steam_openid_lock:
        pending = _pending_steam_openid.pop(state, None)
    if not pending or pending.expires_at <= time.monotonic():
        raise HTTPException(400, "Die Steam-Anmeldung ist abgelaufen oder wurde bereits verwendet.")

    params = dict(request.query_params)
    try:
        steam_id = verify_steam_openid_response(params, pending.callback_url)
        profile = resolve_steam_profile(steam_id)
        if not profile.library_accessible:
            raise ValueError(
                "Die Steam-Spielebibliothek ist nicht öffentlich. Setze die Spieldetails bei Steam auf Öffentlich."
            )
        account = upsert_steam_account(db, pending.participant_id, profile)
        delete_steam_credentials(account.id)
        return _steam_openid_redirect(
            pending,
            steam_openid="success",
            account_id=str(account.id),
        )
    except ValueError as exc:
        return _steam_openid_redirect(pending, steam_openid="error", steam_message=str(exc))
    except Exception:
        return _steam_openid_redirect(
            pending,
            steam_openid="error",
            steam_message="Steam ist gerade nicht erreichbar. Bitte versuche die Anmeldung später erneut.",
        )


def _validated_frontend_origin(origin: str, request: Request) -> str:
    parsed = urlparse(origin.strip())
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise HTTPException(400, "Ungültige Rücksprungadresse für die Steam-Anmeldung.")
    normalized = f"{parsed.scheme}://{parsed.netloc}"
    forwarded_host = (
        request.headers.get("x-forwarded-host")
        or request.headers.get("host")
        or ""
    ).split(",")[0].strip()
    allowed_origins = {value.rstrip("/") for value in settings.cors_origin_list}
    if parsed.netloc != forwarded_host and normalized not in allowed_origins:
        raise HTTPException(400, "Die Rücksprungadresse gehört nicht zu dieser Anwendung.")
    return normalized


def _steam_openid_redirect(pending: PendingSteamOpenId, **query: str) -> RedirectResponse:
    return RedirectResponse(
        url=f"{pending.origin}{pending.return_path}?{urlencode(query)}",
        status_code=303,
    )


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


