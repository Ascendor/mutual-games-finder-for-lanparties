from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings
from app.models import Account, Platform
from app.services.credential_storage import ensure_private_directory, write_private_json

DEVICE_CODE_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode"
TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
XBOX_USER_AUTH_URL = "https://user.auth.xboxlive.com/user/authenticate"
XSTS_AUTH_URL = "https://xsts.auth.xboxlive.com/xsts/authorize"
XBOX_SCOPES = "XboxLive.signin XboxLive.offline_access"


def _auth_path(account_id: int) -> Path:
    path = Path(settings.provider_auth_root) / Platform.xbox.value / str(account_id) / "auth.json"
    ensure_private_directory(path.parent)
    return path


def _load(account_id: int) -> dict[str, Any]:
    path = _auth_path(account_id)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _save(account_id: int, payload: dict[str, Any]) -> None:
    write_private_json(_auth_path(account_id), payload)


def _client_id() -> str:
    value = (settings.xbox_client_id or "").strip()
    if not value:
        raise ValueError(
            "Xbox Live ist auf dem Server noch nicht eingerichtet. "
            "Bitte XBOX_CLIENT_ID in der .env-Datei konfigurieren und die Container neu starten."
        )
    return value


def _response_payload(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except (json.JSONDecodeError, ValueError):
        payload = {}
    return payload if isinstance(payload, dict) else {}


def _raise_provider_error(response: httpx.Response, fallback: str) -> None:
    payload = _response_payload(response)
    detail = payload.get("error_description") or payload.get("Message") or payload.get("message") or payload.get("error")
    raise RuntimeError(str(detail or f"{fallback} (HTTP {response.status_code})"))


def _timestamp(value: Any) -> float:
    if not value:
        return 0
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0


def start_device_login(account: Account) -> dict[str, Any]:
    response = httpx.post(
        DEVICE_CODE_URL,
        data={"client_id": _client_id(), "scope": XBOX_SCOPES},
        params={"mkt": "de-DE"},
        timeout=20,
    )
    if not response.is_success:
        _raise_provider_error(response, "Microsoft-Anmeldung konnte nicht gestartet werden")
    payload = _response_payload(response)
    required = ("device_code", "user_code", "verification_uri", "expires_in")
    if any(not payload.get(key) for key in required):
        raise RuntimeError("Microsoft hat keinen vollständigen Gerätecode geliefert.")

    credentials = _load(account.id)
    credentials["device_flow"] = {
        "device_code": str(payload["device_code"]),
        "user_code": str(payload["user_code"]),
        "verification_uri": str(payload["verification_uri"]),
        "expires_at": time.time() + int(payload["expires_in"]),
        "interval": max(5, int(payload.get("interval") or 5)),
    }
    _save(account.id, credentials)
    return {
        "account_id": account.id,
        "participant_id": account.participant_id,
        "platform": Platform.xbox,
        "login_url": str(payload["verification_uri"]),
        "verification_uri": str(payload["verification_uri"]),
        "user_code": str(payload["user_code"]),
        "expires_in": int(payload["expires_in"]),
        "interval": credentials["device_flow"]["interval"],
        "code_label": "Microsoft-Gerätecode",
        "message": "Microsoft-Anmeldung wurde gestartet.",
    }


def _exchange_xbox_token(oauth: dict[str, Any]) -> dict[str, Any]:
    access_token = str(oauth.get("access_token") or "")
    if not access_token:
        raise RuntimeError("Microsoft hat kein Zugriffstoken geliefert.")

    user_response = httpx.post(
        XBOX_USER_AUTH_URL,
        json={
            "Properties": {
                "AuthMethod": "RPS",
                "SiteName": "user.auth.xboxlive.com",
                "RpsTicket": f"d={access_token}",
            },
            "RelyingParty": "http://auth.xboxlive.com",
            "TokenType": "JWT",
        },
        headers={"Accept": "application/json", "x-xbl-contract-version": "1"},
        timeout=20,
    )
    if not user_response.is_success:
        _raise_provider_error(user_response, "Xbox-Benutzeranmeldung ist fehlgeschlagen")
    user_token = str(_response_payload(user_response).get("Token") or "")
    if not user_token:
        raise RuntimeError("Xbox hat kein Benutzertoken geliefert.")

    xsts_response = httpx.post(
        XSTS_AUTH_URL,
        json={
            "Properties": {"SandboxId": "RETAIL", "UserTokens": [user_token]},
            "RelyingParty": "http://xboxlive.com",
            "TokenType": "JWT",
        },
        headers={"Accept": "application/json", "x-xbl-contract-version": "1"},
        timeout=20,
    )
    if not xsts_response.is_success:
        payload = _response_payload(xsts_response)
        xerr = payload.get("XErr")
        if xerr == 2148916233:
            raise RuntimeError("Dieses Microsoft-Konto hat noch kein Xbox-Profil.")
        if xerr == 2148916238:
            raise RuntimeError("Dieses Xbox-Kinderkonto benötigt die Zustimmung eines Familienorganisators.")
        _raise_provider_error(xsts_response, "Xbox-Live-Anmeldung ist fehlgeschlagen")

    xsts = _response_payload(xsts_response)
    claims = xsts.get("DisplayClaims") if isinstance(xsts.get("DisplayClaims"), dict) else {}
    users = claims.get("xui") if isinstance(claims.get("xui"), list) else []
    profile = users[0] if users and isinstance(users[0], dict) else {}
    token = str(xsts.get("Token") or "")
    user_hash = str(profile.get("uhs") or "")
    xuid = str(profile.get("xid") or profile.get("xuid") or "")
    if not token or not user_hash or not xuid:
        raise RuntimeError("Xbox hat unvollständige Profildaten geliefert.")

    return {
        "xsts_token": token,
        "xsts_expires_at": _timestamp(xsts.get("NotAfter")),
        "user_hash": user_hash,
        "xuid": xuid,
        "gamertag": str(profile.get("gtg") or ""),
    }


def _oauth_credentials(payload: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    previous = previous or {}
    return {
        "oauth_access_token": str(payload.get("access_token") or ""),
        "oauth_refresh_token": str(payload.get("refresh_token") or previous.get("oauth_refresh_token") or ""),
        "oauth_expires_at": time.time() + int(payload.get("expires_in") or 0),
        "oauth_scope": str(payload.get("scope") or previous.get("oauth_scope") or XBOX_SCOPES),
    }


def poll_device_login(account: Account) -> dict[str, Any]:
    credentials = _load(account.id)
    flow = credentials.get("device_flow")
    if not isinstance(flow, dict) or not flow.get("device_code"):
        raise ValueError("Keine laufende Xbox-Anmeldung gefunden. Bitte den Vorgang neu starten.")
    if float(flow.get("expires_at") or 0) <= time.time():
        credentials.pop("device_flow", None)
        _save(account.id, credentials)
        raise ValueError("Der Microsoft-Code ist abgelaufen. Bitte die Xbox-Anmeldung neu starten.")

    response = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": _client_id(),
            "device_code": str(flow["device_code"]),
        },
        timeout=20,
    )
    payload = _response_payload(response)
    if not response.is_success:
        error = str(payload.get("error") or "")
        if error in {"authorization_pending", "slow_down"}:
            if error == "slow_down":
                flow["interval"] = int(flow.get("interval") or 5) + 5
                credentials["device_flow"] = flow
                _save(account.id, credentials)
            return {
                "account_id": account.id,
                "participant_id": account.participant_id,
                "platform": Platform.xbox,
                "authenticated": False,
                "pending": True,
                "interval": int(flow.get("interval") or 5),
                "message": "Warte auf die Bestätigung bei Microsoft.",
            }
        credentials.pop("device_flow", None)
        _save(account.id, credentials)
        if error == "authorization_declined":
            raise ValueError("Die Microsoft-Anmeldung wurde abgebrochen.")
        if error in {"expired_token", "bad_verification_code"}:
            raise ValueError("Der Microsoft-Code ist nicht mehr gültig. Bitte neu starten.")
        _raise_provider_error(response, "Microsoft-Anmeldung ist fehlgeschlagen")

    oauth = _oauth_credentials(payload, credentials)
    xbox = _exchange_xbox_token(payload)
    credentials.update(oauth)
    credentials.update(xbox)
    credentials.pop("device_flow", None)
    _save(account.id, credentials)
    return {
        "account_id": account.id,
        "participant_id": account.participant_id,
        "platform": Platform.xbox,
        "authenticated": True,
        "pending": False,
        "message": "Xbox Live wurde verbunden.",
        "xuid": xbox["xuid"],
        "gamertag": xbox["gamertag"],
    }


def ensure_xbox_credentials(account: Account) -> dict[str, Any]:
    credentials = _load(account.id)
    required = credentials.get("xsts_token") and credentials.get("user_hash") and credentials.get("xuid")
    expires_at = float(credentials.get("xsts_expires_at") or 0)
    if required and (not expires_at or expires_at > time.time() + 60):
        return credentials

    refresh_token = str(credentials.get("oauth_refresh_token") or "")
    if not refresh_token:
        raise RuntimeError("Die Xbox-Anmeldung ist abgelaufen. Bitte Xbox Live erneut verbinden.")
    response = httpx.post(
        TOKEN_URL,
        data={
            "client_id": _client_id(),
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": XBOX_SCOPES,
        },
        timeout=20,
    )
    if not response.is_success:
        raise RuntimeError("Die Xbox-Anmeldung ist abgelaufen. Bitte Xbox Live erneut verbinden.")
    payload = _response_payload(response)
    credentials.update(_oauth_credentials(payload, credentials))
    credentials.update(_exchange_xbox_token(payload))
    _save(account.id, credentials)
    return credentials


def xbox_status(account: Account) -> dict[str, Any]:
    credentials = _load(account.id)
    authenticated = bool(credentials.get("xsts_token") and credentials.get("user_hash") and credentials.get("xuid"))
    return {
        "account_id": account.id,
        "participant_id": account.participant_id,
        "platform": Platform.xbox,
        "authenticated": authenticated,
        "pending": isinstance(credentials.get("device_flow"), dict),
        "message": "Xbox Live ist verbunden." if authenticated else "Xbox Live ist nicht verbunden.",
    }
