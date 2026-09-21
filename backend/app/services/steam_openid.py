from __future__ import annotations

import re
from urllib.parse import urlencode

import httpx


STEAM_OPENID_ENDPOINT = "https://steamcommunity.com/openid/login"
OPENID_NAMESPACE = "http://specs.openid.net/auth/2.0"
OPENID_IDENTIFIER_SELECT = f"{OPENID_NAMESPACE}/identifier_select"
STEAM_CLAIMED_ID_PATTERN = re.compile(
    r"^https?://steamcommunity\.com/openid/id/(?P<steam_id>\d{17})/?$",
    flags=re.IGNORECASE,
)


def build_steam_openid_url(return_to: str, realm: str) -> str:
    query = urlencode(
        {
            "openid.ns": OPENID_NAMESPACE,
            "openid.mode": "checkid_setup",
            "openid.return_to": return_to,
            "openid.realm": realm,
            "openid.identity": OPENID_IDENTIFIER_SELECT,
            "openid.claimed_id": OPENID_IDENTIFIER_SELECT,
        }
    )
    return f"{STEAM_OPENID_ENDPOINT}?{query}"


def verify_steam_openid_response(params: dict[str, str], expected_return_to: str) -> str:
    if params.get("openid.mode") != "id_res":
        raise ValueError("Die Steam-Anmeldung wurde nicht bestätigt.")
    if params.get("openid.ns") != OPENID_NAMESPACE:
        raise ValueError("Steam hat eine unerwartete Anmeldeantwort geliefert.")
    if params.get("openid.op_endpoint") != STEAM_OPENID_ENDPOINT:
        raise ValueError("Die Anmeldeantwort stammt nicht vom erwarteten Steam-Endpunkt.")
    if params.get("openid.return_to") != expected_return_to:
        raise ValueError("Die Steam-Rücksprungadresse stimmt nicht mit der Anmeldung überein.")

    claimed_id = params.get("openid.claimed_id", "")
    if params.get("openid.identity") != claimed_id:
        raise ValueError("Steam hat unterschiedliche Benutzerkennungen geliefert.")
    claimed_match = STEAM_CLAIMED_ID_PATTERN.fullmatch(claimed_id)
    if not claimed_match:
        raise ValueError("Steam hat keine gültige SteamID64 geliefert.")

    verification = {key: value for key, value in params.items() if key.startswith("openid.")}
    verification["openid.mode"] = "check_authentication"
    response = httpx.post(STEAM_OPENID_ENDPOINT, data=verification, timeout=15)
    response.raise_for_status()
    result = {
        key.strip(): value.strip()
        for line in response.text.splitlines()
        if ":" in line
        for key, value in [line.split(":", 1)]
    }
    if result.get("is_valid", "").casefold() != "true":
        raise ValueError("Steam konnte die Anmeldeantwort nicht bestätigen.")
    return claimed_match.group("steam_id")
