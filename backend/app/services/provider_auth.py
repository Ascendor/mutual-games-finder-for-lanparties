from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import time
import uuid
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Account, Platform
from app.services.import_providers import (
    GOG_AUTH_URL,
    GOG_CLIENT_ID,
    GOG_CLIENT_SECRET,
    GOG_EMBED_URL,
    GOG_LOGIN_URL,
    GOG_REDIRECT_URI,
    GOGAuthStore,
    gog_auth_config_path,
    load_provider_auth_json,
    platform_value,
    run_legendary_for_account,
    save_provider_auth_json,
    validate_ea_access_token,
)
from app.services.steam_client_credentials import load_steam_credentials
from app.services.provider_policy import provider_integration_enabled

EPIC_LOGIN_URL = settings.epic_login_url
UBISOFT_APP_ID = settings.ubisoft_app_id
LOGIN_PLATFORMS = {
    Platform.epic,
    Platform.gog,
    Platform.ubisoft,
    Platform.xbox,
    Platform.ea,
    Platform.amazon,
    Platform.battle_net,
    Platform.humble,
    Platform.meta,
}
STATUS_PLATFORMS = LOGIN_PLATFORMS | {Platform.steam}
AMAZON_DEVICE_TYPE = settings.amazon_device_type
AMAZON_LOGIN_URL = settings.amazon_login_url


def _account_platform(account: Account) -> Platform:
    return account.platform if isinstance(account.platform, Platform) else Platform(str(account.platform))


def _provider_error(platform: Platform | str) -> ValueError:
    return ValueError(f"Provider login is not available for {platform_value(platform)}")


def _supported_account(account: Account) -> None:
    if _account_platform(account) not in LOGIN_PLATFORMS:
        raise _provider_error(account.platform)


def _unwrap_pasted_value(value: str) -> str:
    text = value.strip().lstrip("\ufeff")
    fence = re.fullmatch(r"```(?:json|text)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    for _ in range(3):
        if len(text) < 2 or text[0] not in "\"'“”‘’" or text[-1] not in "\"'“”‘’":
            break
        candidate = text[1:-1].strip()
        if text[0] == '"' and text[-1] == '"':
            try:
                decoded = json.loads(text)
                if isinstance(decoded, str):
                    text = decoded.strip()
                    continue
            except json.JSONDecodeError:
                pass
        text = candidate
    return text.strip()


def _extract_case_insensitive(payload: Any, *keys: str) -> Any:
    wanted = {key.casefold() for key in keys}
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key).casefold() in wanted and value not in (None, ""):
                return value
        for value in payload.values():
            found = _extract_case_insensitive(value, *keys)
            if found not in (None, ""):
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _extract_case_insensitive(value, *keys)
            if found not in (None, ""):
                return found
    return None


def _clean_epic_code(code: str) -> str:
    value = _unwrap_pasted_value(code)
    if value.startswith(("{", "[")):
        try:
            payload = json.loads(value)
        except json.JSONDecodeError:
            payload = None
        extracted = _extract_case_insensitive(payload, "authorizationCode", "authorization_code", "code")
        if extracted:
            value = str(extracted)
    elif value.startswith(("http://", "https://")):
        parsed = urlparse(value)
        query = {**parse_qs(parsed.query), **parse_qs(parsed.fragment)}
        value = str(
            (query.get("authorizationCode") or query.get("authorization_code") or query.get("code") or [""])[0]
        )
    else:
        match = re.search(
            r"(?:authorizationCode|authorization_code|code)\s*[:=]\s*[\"'“”‘’]?([^\"'“”‘’\s,}]+)",
            value,
            flags=re.IGNORECASE,
        )
        if match:
            value = match.group(1)
    return _unwrap_pasted_value(value).rstrip(",;")


def _parse_json_or_key_values(code: str) -> dict[str, Any]:
    value = _unwrap_pasted_value(code)
    if not value:
        return {}
    if value.startswith(("{", "[")):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    payload: dict[str, Any] = {}
    for line in value.splitlines():
        separator = "=" if "=" in line else ":" if ":" in line else None
        if separator:
            key, item = line.split(separator, 1)
            payload[key.strip()] = _unwrap_pasted_value(item)
    return payload


def _provider_payload_from_input(code: str, fields: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = _parse_json_or_key_values(code)
    for key, value in (fields or {}).items():
        if value not in (None, "") and key != "code":
            payload.setdefault(key, value)
    return payload


def _extract_browser_cookie(value: str) -> str:
    text = _unwrap_pasted_value(value)
    if not text:
        return ""
    if text.startswith(("[", "{")):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = None
        cookie_items = payload if isinstance(payload, list) else payload.get("cookies") if isinstance(payload, dict) else None
        if isinstance(cookie_items, list):
            cookies = [
                f"{item['name']}={item['value']}"
                for item in cookie_items
                if isinstance(item, dict) and item.get("name") and item.get("value") is not None
            ]
            if cookies:
                return "; ".join(cookies)
    for pattern in (
        r"""(?:-H|--header)\s+(?:"Cookie:\s*([^"]+)"|'Cookie:\s*([^']+)')""",
        r"""(?:-b|--cookie)\s+(?:"([^"]+)"|'([^']+)')""",
        r"""Cookie:\s*([^\r\n]+)""",
    ):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            cookie = next((group.strip() for group in match.groups() if group), "")
            return re.sub(r"\^(?=[&|<>()^$!])", "", cookie)
    if re.search(r"(?:^|;\s*)[\w.-]+=", text):
        cookie = text.removeprefix("Cookie:").strip()
        return re.sub(r"\^(?=[&|<>()^$!])", "", cookie)
    return ""


def _extract_ea_bearer(value: str) -> str:
    text = _unwrap_pasted_value(value)
    if not text:
        return ""
    normalized = re.sub(r"\^(?=[\"'&|<>()^$!])", "", text)
    if normalized.startswith(("{", "[")):
        try:
            payload = json.loads(normalized)
        except json.JSONDecodeError:
            payload = None
        authorization = _extract_case_insensitive(payload, "authorization")
        if authorization:
            normalized = str(authorization)
    curl_input = bool(re.search(r"(?:^|\s)curl(?:\.exe)?(?:\s|$)", normalized, flags=re.IGNORECASE))
    if curl_input and "service-aggregation-layer.juno.ea.com/graphql" not in normalized.casefold():
        raise ValueError(
            "Das ist nicht die EA-Bibliotheksanfrage. Filtere im Netzwerk-Tab nach "
            "'juno.ea.com/graphql' und kopiere diese Anfrage als cURL."
        )
    match = re.search(
        r"""Authorization\s*:\s*Bearer\s+([^\s"'\\]+)""",
        normalized,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1).rstrip("^")
    match = re.fullmatch(r"""(?:Bearer\s+)?([^\s"'\\]{20,})""", normalized, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def _cookie_value(cookie_header: str, name: str) -> str | None:
    for item in cookie_header.split(";"):
        key, separator, value = item.strip().partition("=")
        if separator and key == name:
            return value.strip()
    return None


def _amazon_login(account: Account) -> dict[str, Any]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("utf-8")).digest()).decode("ascii").rstrip("=")
    device_serial = uuid.uuid1().hex.upper()
    client_id = f"{device_serial}#{AMAZON_DEVICE_TYPE}".encode("ascii").hex()
    save_provider_auth_json(
        Platform.amazon,
        account.id,
        {
            "pending_code_verifier": verifier,
            "pending_client_id": client_id,
            "device_serial": device_serial,
        },
    )
    params = {
        "openid.ns": "http://specs.openid.net/auth/2.0",
        "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
        "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
        "openid.mode": "checkid_setup",
        "openid.oa2.scope": "device_auth_access",
        "openid.ns.oa2": "http://www.amazon.com/ap/ext/oauth/2",
        "openid.oa2.response_type": "code",
        "openid.oa2.code_challenge_method": "S256",
        "openid.oa2.client_id": f"device:{client_id}",
        "language": "en_US",
        "marketPlaceId": "ATVPDKIKX0DER",
        "openid.return_to": "https://www.amazon.com",
        "openid.pape.max_auth_age": "0",
        "openid.assoc_handle": "amzn_sonic_games_launcher",
        "pageId": "amzn_sonic_games_launcher",
        "openid.oa2.code_challenge": challenge,
    }
    return {
        "account_id": account.id,
        "participant_id": account.participant_id,
        "platform": Platform.amazon,
        "login_url": f"{AMAZON_LOGIN_URL}?{urlencode(params)}",
        "code_label": "Adresse nach der Anmeldung",
        "message": "Nach der Amazon-Anmeldung die vollständige Adresse der letzten Seite kopieren.",
    }


def _pick_first(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return None


def _identity_from_payload(payload: dict[str, Any]) -> dict[str, str]:
    account_id = _extract_case_insensitive(
        payload,
        "userId",
        "user_id",
        "profileId",
        "profile_id",
        "accountId",
        "account_id",
        "customer_id",
        "xuid",
    )
    display_name = _extract_case_insensitive(
        payload,
        "displayName",
        "display_name",
        "username",
        "userName",
        "nameOnPlatform",
        "gamertag",
        "nickname",
    )
    identity: dict[str, str] = {}
    if account_id not in (None, ""):
        identity["provider_account_id"] = str(account_id)
    if display_name not in (None, ""):
        identity["provider_display_name"] = str(display_name)
    return identity


def _epic_identity_from_output(output: str) -> dict[str, str]:
    match = re.search(r'(?:logged in|login successful).*?(?:as|for)\s+["\']([^"\']+)["\']', output, re.IGNORECASE)
    if not match:
        match = re.search(r'Epic account:\s*(.+)', output, re.IGNORECASE)
    return {"provider_display_name": match.group(1).strip()} if match else {}


def _ubisoft_profile_id(payload: dict[str, Any], account: Account) -> str | None:
    value = _pick_first(payload, "profileId", "profile_id", "userId", "user_id", "accountId", "account_id", "id")
    if value:
        return str(value)
    for nested_key in ("profile", "user", "account"):
        nested = payload.get(nested_key)
        if isinstance(nested, dict):
            value = _pick_first(nested, "profileId", "profile_id", "userId", "user_id", "accountId", "account_id", "id")
            if value:
                return str(value)
    if account.account_id and not str(account.account_id).startswith("local-"):
        return account.account_id
    return None


def _ubisoft_ticket(payload: dict[str, Any]) -> str | None:
    return _pick_first(payload, "ticket", "access_token", "accessToken")


def _ubisoft_2fa_ticket(payload: dict[str, Any]) -> str | None:
    return _pick_first(payload, "twoFactorAuthenticationTicket", "twoFactorTicket", "two_factor_ticket", "2faTicket")


def _ubisoft_error(payload: dict[str, Any]) -> str | None:
    value = _pick_first(payload, "error", "errorCode", "message", "detail")
    return str(value) if value else None



def _ubisoft_session_request(email: str, password: str, payload: dict[str, Any]) -> dict[str, Any]:
    basic = base64.b64encode(f"{email}:{password}".encode("utf-8")).decode("ascii")
    app_id = str(payload.get("appId") or UBISOFT_APP_ID)
    two_factor_code = _pick_first(payload, "twoFactorCode", "two_factor_code", "otp")
    two_factor_ticket = _ubisoft_2fa_ticket(payload)
    attempts: list[dict[str, str]] = []
    base_headers = {
        "Authorization": f"Basic {basic}",
        "Ubi-AppId": app_id,
        "User-Agent": f"UbisoftConnect/1.0 {settings.app_client_identifier}",
    }
    if two_factor_code:
        headers = dict(base_headers)
        headers["Ubi-2FACode"] = str(two_factor_code)
        headers["Ubi-2FARememberDevice"] = "true"
        attempts.append(headers)
        if two_factor_ticket:
            headers = dict(base_headers)
            headers["Ubi-2FACode"] = str(two_factor_code)
            headers["Ubi-2FATicket"] = str(two_factor_ticket)
            headers["Ubi-2FARememberDevice"] = "true"
            attempts.append(headers)
            headers = {
                "Authorization": f"ubi_2fa_v1 t={two_factor_ticket}",
                "Ubi-AppId": app_id,
                "Ubi-2FACode": str(two_factor_code),
                "Ubi-2FARememberDevice": "true",
                "User-Agent": f"UbisoftConnect/1.0 {settings.app_client_identifier}",
            }
            attempts.append(headers)
    else:
        attempts.append(base_headers)

    last_payload: dict[str, Any] = {}
    last_response: httpx.Response | None = None
    for headers in attempts:
        response = httpx.post(
            "https://public-ubiservices.ubi.com/v3/profiles/sessions",
            headers=headers,
            json={"rememberMe": True},
            timeout=30,
        )
        try:
            response_payload = response.json()
        except Exception:
            response_payload = {"message": response.text}
        last_payload = response_payload if isinstance(response_payload, dict) else {"message": str(response_payload)}
        last_response = response
        if response.is_success and (_ubisoft_ticket(last_payload) or not _ubisoft_2fa_ticket(last_payload)):
            return last_payload
        if two_factor_code and _ubisoft_ticket(last_payload):
            return last_payload
    if last_response is not None and not last_response.is_success and not _ubisoft_2fa_ticket(last_payload):
        last_response.raise_for_status()
    return last_payload
def gog_login_url() -> str:
    params = {
        "client_id": GOG_CLIENT_ID,
        "redirect_uri": GOG_REDIRECT_URI,
        "response_type": "code",
        "layout": "client2",
    }
    return f"{GOG_LOGIN_URL}?{urlencode(params)}"


def _clean_gog_code(value: str) -> str:
    text = _unwrap_pasted_value(value)
    if not text:
        return ""
    if text.startswith(("{", "[")):
        payload = json.loads(text)
        text = str(_extract_case_insensitive(payload, "code", "authorizationCode") or "").strip()
    elif text.startswith("http://") or text.startswith("https://"):
        parsed = urlparse(text)
        query = {**parse_qs(parsed.query), **parse_qs(parsed.fragment)}
        text = (query.get("code") or query.get("authorizationCode") or [""])[0].strip()
    else:
        match = re.search(r"(?:code|authorizationCode)\s*[:=]\s*[\"'“”‘’]?([^\"'“”‘’\s,}]+)", text)
        if match:
            text = match.group(1)
    return _unwrap_pasted_value(text).rstrip(",;")


def epic_status(account: Account) -> dict[str, Any]:
    result = run_legendary_for_account(account, ["status"], timeout=20)
    output = f"{result.stdout}\n{result.stderr}".strip()
    authenticated = result.returncode == 0 and "not logged in" not in output.casefold()
    return {
        "account_id": account.id,
        "participant_id": account.participant_id,
        "platform": _account_platform(account),
        "authenticated": authenticated,
        "message": output.splitlines()[0] if output else "Legendary status checked",
    }


def gog_status(account: Account) -> dict[str, Any]:
    store = GOGAuthStore(str(gog_auth_config_path(account.id)))
    credentials = store._load_all().get(GOG_CLIENT_ID)
    authenticated = bool(credentials and credentials.get("access_token") and not store.is_expired(credentials))
    return {
        "account_id": account.id,
        "participant_id": account.participant_id,
        "platform": _account_platform(account),
        "authenticated": authenticated,
        "message": "GOG auth cache is ready" if authenticated else "GOG is not connected",
    }


def generic_json_status(account: Account) -> dict[str, Any]:
    platform = _account_platform(account)
    try:
        credentials = load_provider_auth_json(platform, account.id)
    except Exception:
        credentials = {}
    label = platform_value(platform)
    authenticated = bool(credentials)
    needs_2fa = False
    if platform == Platform.ubisoft:
        authenticated = bool(_ubisoft_ticket(credentials) and _ubisoft_profile_id(credentials, account))
        needs_2fa = bool(credentials.get("pending_2fa_ticket")) and not authenticated
    elif platform == Platform.amazon:
        authenticated = bool(credentials.get("access_token") and credentials.get("refresh_token"))
    elif platform in {Platform.battle_net, Platform.humble}:
        authenticated = bool(credentials.get("cookie"))
    elif platform == Platform.meta:
        authenticated = bool(credentials.get("access_token"))
    elif platform == Platform.ea:
        authenticated = bool(credentials.get("access_token"))
    message = f"{label} auth data is stored" if authenticated else f"{label} is not connected"
    if needs_2fa:
        message = "Ubisoft wartet auf 2FA-Code"
    return {
        "account_id": account.id,
        "participant_id": account.participant_id,
        "platform": platform,
        "authenticated": authenticated,
        "needs_2fa": needs_2fa,
        "message": message,
    }


def account_status(account: Account) -> dict[str, Any]:
    platform = _account_platform(account)
    if platform == Platform.steam:
        authenticated = load_steam_credentials(account.id) is not None
        is_direct_connection = bool(re.fullmatch(r"\d{17}", account.account_id or ""))
        connection_mode = "qr" if authenticated else "community" if is_direct_connection else None
        return {
            "account_id": account.id,
            "participant_id": account.participant_id,
            "platform": platform,
            "authenticated": authenticated,
            "needs_2fa": False,
            "connection_mode": connection_mode,
            "message": (
                "Steam QR login is stored"
                if authenticated
                else "Steam Community ID without login token"
                if is_direct_connection
                else "Steam was imported without a direct connection"
            ),
            "available": True,
        }
    _supported_account(account)
    if not provider_integration_enabled(platform):
        return {
            "account_id": account.id,
            "participant_id": account.participant_id,
            "platform": platform,
            "authenticated": False,
            "needs_2fa": False,
            "available": False,
            "message": "Inoffizielle Provider-Anbindung ist serverseitig deaktiviert",
        }
    if platform == Platform.epic:
        result = epic_status(account)
    elif platform == Platform.gog:
        result = gog_status(account)
    elif platform == Platform.xbox:
        from app.services.xbox_auth import xbox_status

        result = xbox_status(account)
    else:
        result = generic_json_status(account)
    result["available"] = True
    return result


def status(db: Session) -> list[dict[str, Any]]:
    accounts = db.scalars(select(Account).where(Account.platform.in_(STATUS_PLATFORMS)).order_by(Account.platform, Account.display_name)).all()
    return [account_status(account) for account in accounts]


def start(account: Account) -> dict[str, Any]:
    _supported_account(account)
    platform = _account_platform(account)
    if platform == Platform.epic:
        return {
            "account_id": account.id,
            "participant_id": account.participant_id,
            "platform": platform,
            "login_url": EPIC_LOGIN_URL,
            "code_label": "authorizationCode",
            "message": "Open the Legendary Epic login page and paste the authorizationCode from the JSON response.",
        }
    if platform == Platform.gog:
        return {
            "account_id": account.id,
            "participant_id": account.participant_id,
            "platform": platform,
            "login_url": gog_login_url(),
            "code_label": "Redirect-URL oder code",
            "message": "GOG Login oeffnen und danach die komplette Redirect-URL einfuegen; die App liest den code selbst aus.",
        }
    if platform == Platform.ubisoft:
        return {
            "account_id": account.id,
            "participant_id": account.participant_id,
            "platform": platform,
            "login_url": "https://connect.ubisoft.com/",
            "code_label": "Ubisoft Login",
            "message": "E-Mail und Passwort eintragen. Falls Ubisoft 2FA verlangt, bleibt das Ticket gespeichert und danach reicht der 2FA-Code.",
        }
    if platform == Platform.xbox:
        from app.services.xbox_auth import start_device_login

        return start_device_login(account)
    if platform == Platform.ea:
        return {
            "account_id": account.id,
            "participant_id": account.participant_id,
            "platform": platform,
            "login_url": "https://www.ea.com/login",
            "capture_url": "https://www.ea.com/sales/deals",
            "code_label": "Kopierte EA-Bibliotheksanfrage",
            "message": "Bei EA anmelden und die GraphQL-Bibliotheksanfrage als cURL kopieren.",
        }
    if platform == Platform.amazon:
        return _amazon_login(account)
    if platform == Platform.battle_net:
        return {
            "account_id": account.id,
            "participant_id": account.participant_id,
            "platform": platform,
            "login_url": "https://account.battle.net/api/games-and-subs",
            "code_label": "Kopierte Browser-Anfrage",
            "message": "Bei Battle.net anmelden und die Bibliotheksanfrage als cURL kopieren.",
        }
    if platform == Platform.humble:
        return {
            "account_id": account.id,
            "participant_id": account.participant_id,
            "platform": platform,
            "login_url": "https://www.humblebundle.com/home/library?hmb_source=navbar",
            "code_label": "Kopierte Browser-Anfrage",
            "message": "Bei Humble anmelden und die Bibliotheksanfrage als cURL kopieren.",
        }
    if platform == Platform.meta:
        return {
            "account_id": account.id,
            "participant_id": account.participant_id,
            "platform": platform,
            "login_url": "https://secure.oculus.com/my/profile/",
            "code_label": "Kopierte Browser-Anfrage",
            "message": "Bei Meta anmelden und die Profilanfrage als cURL kopieren.",
        }
    raise _provider_error(platform)


def complete_epic(account: Account, code: str) -> dict[str, Any]:
    auth_code = _clean_epic_code(code)
    if not auth_code:
        raise RuntimeError("Epic authorizationCode is empty")
    result = run_legendary_for_account(account, ["auth", "--code", auth_code], timeout=90)
    output = f"{result.stdout}\n{result.stderr}".strip()
    if result.returncode != 0:
        raise RuntimeError(output or "Epic authentication failed")
    return {
        "account_id": account.id,
        "participant_id": account.participant_id,
        "platform": _account_platform(account),
        "authenticated": True,
        "message": output or "Epic connected",
        **_epic_identity_from_output(output),
    }


def complete_gog(account: Account, code: str, redirect_uri: str = GOG_REDIRECT_URI) -> dict[str, Any]:
    auth_code = _clean_gog_code(code)
    if not auth_code:
        raise RuntimeError("GOG authorization code is empty")
    params = {"client_id": GOG_CLIENT_ID, "client_secret": GOG_CLIENT_SECRET, "grant_type": "authorization_code", "code": auth_code, "redirect_uri": redirect_uri}
    response = httpx.get(GOG_AUTH_URL, params=params, timeout=30)
    response.raise_for_status()
    credentials = response.json()
    credentials["loginTime"] = time.time()
    store = GOGAuthStore(str(gog_auth_config_path(account.id)))
    all_credentials = store._load_all()
    all_credentials[GOG_CLIENT_ID] = credentials
    store._save_all(all_credentials)
    identity = _identity_from_payload(credentials)
    try:
        profile_response = httpx.get(
            f"{GOG_EMBED_URL}/userData.json",
            headers={"Authorization": f"Bearer {credentials['access_token']}"},
            timeout=20,
        )
        if profile_response.is_success:
            profile = profile_response.json()
            if isinstance(profile, dict):
                identity.update(_identity_from_payload(profile))
    except Exception:
        pass
    return {
        "account_id": account.id,
        "participant_id": account.participant_id,
        "platform": _account_platform(account),
        "authenticated": True,
        "message": "GOG connected",
        **identity,
    }


def complete_amazon(account: Account, value: str) -> dict[str, Any]:
    pasted = _unwrap_pasted_value(value)
    parsed = urlparse(pasted)
    query = {**parse_qs(parsed.query), **parse_qs(parsed.fragment)}
    authorization_code = str(
        (query.get("openid.oa2.authorization_code") or query.get("authorization_code") or query.get("code") or [""])[0]
    ).strip()
    if not authorization_code:
        match = re.search(r"openid\.oa2\.authorization_code[=:]\s*([^&\s]+)", pasted)
        authorization_code = match.group(1) if match else ""
    pending = load_provider_auth_json(Platform.amazon, account.id)
    verifier = pending.get("pending_code_verifier")
    client_id = pending.get("pending_client_id")
    if not authorization_code or not verifier or not client_id:
        raise RuntimeError("Amazon-Bestätigungscode fehlt. Bitte die vollständige Adresse nach der Anmeldung einfügen.")
    request_data = {
        "auth_data": {
            "use_global_authentication": False,
            "authorization_code": authorization_code,
            "code_verifier": verifier,
            "code_algorithm": "SHA-256",
            "client_id": client_id,
            "client_domain": "DeviceLegacy",
        },
        "registration_data": {
            "app_name": "AGSLauncher for Windows",
            "app_version": "1.0.0",
            "device_model": "Windows",
            "device_name": None,
            "device_serial": pending.get("device_serial") or secrets.token_hex(16),
            "device_type": AMAZON_DEVICE_TYPE,
            "domain": "Device",
            "os_version": "10.0.19044.0",
        },
        "requested_extensions": ["customer_info", "device_info"],
        "requested_token_type": ["bearer", "mac_dms"],
        "user_context_map": {},
    }
    response = httpx.post(
        "https://api.amazon.com/auth/register",
        json=request_data,
        headers={"User-Agent": "AGSLauncher/1.0.0"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    bearer = (
        payload.get("response", {})
        .get("success", {})
        .get("tokens", {})
        .get("bearer", {})
    )
    if not bearer.get("access_token") or not bearer.get("refresh_token"):
        raise RuntimeError("Amazon hat keine verwendbare Anmeldung zurückgegeben.")
    bearer["expires_at"] = time.time() + float(bearer.get("expires_in") or 3600)
    bearer["device_serial"] = request_data["registration_data"]["device_serial"]
    save_provider_auth_json(Platform.amazon, account.id, bearer)
    identity = _identity_from_payload(payload)
    return {
        "account_id": account.id,
        "participant_id": account.participant_id,
        "platform": Platform.amazon,
        "authenticated": True,
        "message": "Amazon Games verbunden",
        **identity,
    }


def complete_browser_session(account: Account, value: str) -> dict[str, Any]:
    platform = _account_platform(account)
    cookie = _extract_browser_cookie(value)
    if not cookie:
        raise RuntimeError(
            "Keine Browser-Sitzung erkannt. Bitte im Netzwerk-Tab die angegebene Anfrage mit "
            "„Kopieren > Als cURL kopieren“ übernehmen und vollständig einfügen."
        )
    if platform == Platform.meta:
        access_token = _cookie_value(cookie, "oc_ac_at")
        if not access_token:
            raise RuntimeError("In der kopierten Meta-Anfrage fehlt das Cookie oc_ac_at. Bitte die Profilseite neu laden und erneut kopieren.")
        credentials = {"access_token": access_token}
    else:
        credentials = {"cookie": cookie}
    save_provider_auth_json(platform, account.id, credentials)
    return {
        "account_id": account.id,
        "participant_id": account.participant_id,
        "platform": platform,
        "authenticated": True,
        "message": f"{platform_value(platform)} verbunden",
    }


def complete_ubisoft(account: Account, code: str, fields: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = _provider_payload_from_input(code, fields)
    try:
        stored = load_provider_auth_json(Platform.ubisoft, account.id)
    except Exception:
        stored = {}
    pending_ticket = stored.get("pending_2fa_ticket")
    if pending_ticket and not _ubisoft_2fa_ticket(payload):
        payload["twoFactorTicket"] = pending_ticket
    submitted_2fa_code = bool(_pick_first(payload, "twoFactorCode", "two_factor_code", "otp"))
    if payload.get("email") and payload.get("password"):
        payload = _ubisoft_session_request(str(payload["email"]), str(payload["password"]), payload)
    challenge_ticket = _ubisoft_2fa_ticket(payload)
    ticket = _ubisoft_ticket(payload)
    profile_id = _ubisoft_profile_id(payload, account)
    if challenge_ticket and not ticket:
        save_provider_auth_json(Platform.ubisoft, account.id, {"pending_2fa_ticket": str(challenge_ticket)})
        message = "Ubisoft verlangt 2FA. Bitte 2FA-Code eingeben und erneut bestaetigen."
        if submitted_2fa_code:
            message = "Ubisoft hat den 2FA-Code nicht akzeptiert oder ein neues Ticket angefordert. Bitte aktuellen 2FA-Code erneut eingeben."
        return {"account_id": account.id, "participant_id": account.participant_id, "platform": Platform.ubisoft, "authenticated": False, "needs_2fa": True, "message": message}
    if not ticket:
        error = _ubisoft_error(payload)
        keys = ", ".join(sorted(payload.keys())) or "keine"
        raise RuntimeError(error or f"Ubisoft login returned no ticket. Antwort-Felder: {keys}")
    if not profile_id:
        keys = ", ".join(sorted(payload.keys())) or "keine"
        raise RuntimeError(f"Ubisoft login returned no profileId/userId. Antwort-Felder: {keys}")
    payload.pop("pending_2fa_ticket", None)
    payload["ticket"] = ticket
    payload["profileId"] = profile_id
    save_provider_auth_json(Platform.ubisoft, account.id, payload)
    return {
        "account_id": account.id,
        "participant_id": account.participant_id,
        "platform": Platform.ubisoft,
        "authenticated": True,
        "needs_2fa": False,
        "message": "Ubisoft connected",
        **_identity_from_payload(payload),
    }


def complete_generic_json(account: Account, code: str, fields: dict[str, Any] | None = None) -> dict[str, Any]:
    platform = _account_platform(account)
    payload = _provider_payload_from_input(code, fields)
    if not payload:
        raise RuntimeError(f"{platform_value(platform)} auth data is empty")
    save_provider_auth_json(platform, account.id, payload)
    return {"account_id": account.id, "participant_id": account.participant_id, "platform": platform, "authenticated": True, "message": f"{platform_value(platform)} connected"}


def complete_ea(account: Account, code: str) -> dict[str, Any]:
    token = _extract_ea_bearer(code)
    if not token:
        raise ValueError(
            "In der kopierten Anfrage fehlt der EA-Bearer-Token. Kopiere im Netzwerk-Tab eine erfolgreiche "
            "Anfrage an 'service-aggregation-layer.juno.ea.com/graphql' vollständig als cURL."
        )
    data = validate_ea_access_token(token)
    save_provider_auth_json(
        Platform.ea,
        account.id,
        {
            "access_token": token,
            "captured_at": int(time.time()),
        },
    )
    me = data.get("me") if isinstance(data.get("me"), dict) else {}
    identity = _identity_from_payload(me)
    if me.get("id"):
        identity["provider_account_id"] = str(me["id"])
    return {
        "account_id": account.id,
        "participant_id": account.participant_id,
        "platform": Platform.ea,
        "authenticated": True,
        "message": "EA wurde verbunden. Die Bibliothek wird jetzt geladen.",
        **identity,
    }


def complete(account: Account, code: str, fields: dict[str, Any] | None = None) -> dict[str, Any]:
    _supported_account(account)
    platform = _account_platform(account)
    if platform == Platform.epic:
        return complete_epic(account, code)
    if platform == Platform.gog:
        return complete_gog(account, code)
    if platform == Platform.ubisoft:
        return complete_ubisoft(account, code, fields)
    if platform == Platform.ea:
        return complete_ea(account, code)
    if platform == Platform.amazon:
        return complete_amazon(account, code)
    if platform in {Platform.battle_net, Platform.humble, Platform.meta}:
        return complete_browser_session(account, code)
    return complete_generic_json(account, code, fields)


def poll(account: Account) -> dict[str, Any]:
    _supported_account(account)
    if _account_platform(account) != Platform.xbox:
        raise ValueError("Dieser Anmeldeablauf ist nur für Xbox Live verfügbar.")
    from app.services.xbox_auth import poll_device_login

    return poll_device_login(account)


def logout(account: Account) -> dict[str, Any]:
    _supported_account(account)
    platform = _account_platform(account)
    if platform == Platform.epic:
        result = run_legendary_for_account(account, ["auth", "--delete"], timeout=30)
        output = f"{result.stdout}\n{result.stderr}".strip()
        return {"account_id": account.id, "participant_id": account.participant_id, "platform": platform, "authenticated": False, "message": output or "Epic disconnected"}
    if platform == Platform.gog:
        store = GOGAuthStore(str(gog_auth_config_path(account.id)))
        credentials = store._load_all()
        credentials.pop(GOG_CLIENT_ID, None)
        store._save_all(credentials)
    else:
        save_provider_auth_json(platform, account.id, {})
    return {"account_id": account.id, "participant_id": account.participant_id, "platform": platform, "authenticated": False, "message": f"{platform_value(platform)} disconnected"}


