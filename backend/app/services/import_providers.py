from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote, urlencode

import httpx
import yaml

from app.core.config import settings
from app.models import Account, Platform
from app.services.account_identity import apply_account_identity, is_placeholder_display_name
from app.services.credential_storage import ensure_private_directory, write_private_json
from app.services.game_classification import classify_game
from app.services.normalization import normalize_title
from app.services.steam_client_credentials import load_authenticated_steam_library

GOG_CLIENT_ID = settings.gog_client_id
GOG_CLIENT_SECRET = settings.gog_client_secret
GOG_AUTH_URL = settings.gog_auth_url
GOG_LOGIN_URL = settings.gog_login_url
GOG_REDIRECT_URI = settings.gog_redirect_uri
GOG_EMBED_URL = settings.gog_embed_url
GOG_API_URL = settings.gog_api_url
GOG_DEFAULT_CACHE = Path.home() / ".config" / "heroic_gogdl" / "auth.json"
AMAZON_ENTITLEMENTS_URL = settings.amazon_entitlements_url
AMAZON_TOKEN_URL = settings.amazon_token_url
EA_GRAPHQL_URL = settings.ea_graphql_url
EA_OWNED_GAMES_QUERY_HASH = settings.ea_owned_games_query_hash
EA_PLAY_TIMES_QUERY_HASH = settings.ea_play_times_query_hash
EA_IDENTITY_URL = settings.ea_identity_url
EA_ORIGIN_API_BASE_URLS = tuple(
    url.strip().rstrip("/")
    for url in settings.ea_origin_api_base_urls.split(",")
    if url.strip()
)
LOGGER = logging.getLogger(__name__)

def platform_value(platform: Platform | str) -> str:
    return platform.value if isinstance(platform, Platform) else str(platform)


def coerce_platform(platform: Platform | str) -> Platform:
    return platform if isinstance(platform, Platform) else Platform(str(platform))


def provider_auth_dir(platform: Platform, account_id: int) -> Path:
    path = Path(settings.provider_auth_root) / platform_value(platform) / str(account_id)
    return ensure_private_directory(path)



def provider_auth_json_path(platform: Platform, account_id: int) -> Path:
    return provider_auth_dir(platform, account_id) / "auth.json"


def load_provider_auth_json(platform: Platform, account_id: int) -> dict[str, Any]:
    path = provider_auth_json_path(platform, account_id)
    if not path.exists():
        raise RuntimeError(f"{platform_value(platform)} is not connected. Open Provider-Logins and complete the account login first.")
    return json.loads(path.read_text(encoding="utf-8"))


def save_provider_auth_json(platform: Platform, account_id: int, payload: dict[str, Any]) -> None:
    path = provider_auth_json_path(platform, account_id)
    write_private_json(path, payload)


def _ea_graphql_url(operation_name: str, variables: dict[str, Any], query_hash: str) -> str:
    query = urlencode(
        {
            "operationName": operation_name,
            "variables": json.dumps(variables, separators=(",", ":")),
            "extensions": json.dumps(
                {
                    "persistedQuery": {
                        "version": 1,
                        "sha256Hash": query_hash,
                    }
                },
                separators=(",", ":"),
            ),
        }
    )
    return f"{EA_GRAPHQL_URL}?{query}"


def ea_owned_games_url(offset: str = "0", limit: int = 500) -> str:
    return _ea_graphql_url(
        "getPreloadedOwnedGames",
        {
            "isMac": False,
            "addFieldsToPreloadGames": True,
            "locale": "en",
            "limit": limit,
            "next": offset,
            "type": ["DIGITAL_FULL_GAME", "PACKAGED_FULL_GAME"],
            "entitlementEnabled": True,
            "storefronts": ["EA", "STEAM", "EPIC"],
            "ownershipMethods": [
                "UNKNOWN",
                "ASSOCIATION",
                "PURCHASE",
                "REDEMPTION",
                "GIFT_RECEIPT",
                "ENTITLEMENT_GRANT",
                "DIRECT_ENTITLEMENT",
                "PRE_ORDER_PURCHASE",
                "VAULT",
                "XGP_VAULT",
                "STEAM",
                "STEAM_VAULT",
                "STEAM_SUBSCRIPTION",
                "EPIC",
                "EPIC_VAULT",
                "EPIC_SUBSCRIPTION",
            ],
            "platforms": ["PC"],
        },
        EA_OWNED_GAMES_QUERY_HASH,
    )


def ea_request_headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "AuthToken": access_token,
        "X-AuthToken": access_token,
        "Accept": "application/json",
        "Origin": "https://www.ea.com",
        "Referer": "https://www.ea.com/",
        "User-Agent": f"Mozilla/5.0 {settings.app_client_identifier}/1.0",
        "X-Request-Source": "SPA",
    }


def _ea_graphql_data(response: httpx.Response, operation_name: str) -> dict[str, Any]:
    if response.status_code in {401, 403}:
        raise RuntimeError("Die EA-Anmeldung ist abgelaufen. Bitte EA erneut verbinden.")
    response.raise_for_status()
    payload = response.json()
    errors = payload.get("errors") if isinstance(payload, dict) else None
    if errors:
        message = next(
            (
                str(item.get("message"))
                for item in errors
                if isinstance(item, dict) and item.get("message")
            ),
            "unbekannter GraphQL-Fehler",
        )
        raise RuntimeError(f"EA {operation_name} fehlgeschlagen: {message}")
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise RuntimeError(f"EA {operation_name} hat keine verwertbaren Daten geliefert.")
    return data


def validate_ea_access_token(access_token: str) -> dict[str, Any]:
    response = httpx.get(
        ea_owned_games_url(limit=1),
        headers=ea_request_headers(access_token),
        timeout=30,
    )
    data = _ea_graphql_data(response, "Anmeldung")
    me = data.get("me")
    owned_games = me.get("ownedGameProducts") if isinstance(me, dict) else None
    if not isinstance(owned_games, dict) or not isinstance(owned_games.get("items"), list):
        raise RuntimeError(
            "EA hat die Bibliothek nicht freigegeben. Kopiere eine neue erfolgreiche "
            "GraphQL-Anfrage an 'service-aggregation-layer.juno.ea.com'."
        )
    return data


def _cookie_headers(credentials: dict[str, Any]) -> dict[str, str]:
    cookie = str(credentials.get("cookie") or credentials.get("cookies") or "").strip()
    if not cookie:
        raise RuntimeError("Die gespeicherte Browser-Sitzung fehlt. Bitte den Account neu verbinden.")
    # Firefox escapes Windows cmd metacharacters when copying a request as cURL.
    cookie = re.sub(r"\^(?=[&|<>()^$!])", "", cookie)
    return {
        "Cookie": cookie,
        "User-Agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) {settings.app_client_identifier}/1.0",
        "Accept": "application/json, text/plain, */*",
    }


def _collect_game_candidates(payload: Any) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[int] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            title = _first(value, "title", "name", "displayName", "display_name", "productTitle", "product_title")
            identifier = _first(value, "id", "titleId", "title_id", "productId", "product_id", "gameId", "game_id", "contentId", "content_id")
            if title and identifier and id(value) not in seen:
                seen.add(id(value))
                candidates.append(value)
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(payload)
    return candidates


def _games_from_payload(payload: Any, fallback_prefix: str) -> list[ImportedGame]:
    games: list[ImportedGame] = []
    for index, item in enumerate(_collect_game_candidates(payload)):
        game = _game_from_mapping(item, fallback_platform_id=f"{fallback_prefix}-{index}")
        if game:
            games.append(game)
    return games


def _xbox_pc_games_from_payload(payload: Any) -> list[ImportedGame]:
    if not isinstance(payload, dict) or not isinstance(payload.get("titles"), list):
        return []
    games: list[ImportedGame] = []
    seen: set[str] = set()
    for item in payload["titles"]:
        if not isinstance(item, dict):
            continue
        devices = {
            str(device).strip().casefold()
            for device in item.get("devices", [])
            if device not in (None, "")
        }
        if "pc" not in devices:
            continue
        content_type = str(item.get("type") or "Game").strip().casefold()
        if content_type != "game":
            continue
        platform_id = str(item.get("pfn") or item.get("titleId") or item.get("id") or "").strip()
        title = str(item.get("name") or item.get("title") or "").strip()
        if not platform_id or not title or platform_id in seen:
            continue
        seen.add(platform_id)
        detail = item.get("detail") if isinstance(item.get("detail"), dict) else {}
        games.append(
            ImportedGame(
                platform_game_id=platform_id,
                title=title,
                playtime_minutes=_as_int(item.get("minutesPlayed"), 0),
                description=str(detail.get("description") or ""),
                cover_url=item.get("displayImage") or detail.get("image"),
                release_date=_parse_date(detail.get("releaseDate")),
                genres=_as_list(detail.get("genres") or detail.get("genre")),
                feature_metadata_known=False,
            )
        )
    return games


def _ubisoft_is_non_game(details: dict[str, Any]) -> bool:
    title = str(_first(details, "displayName", "name", default="") or "").casefold()
    platform = str(_first(details, "platform", "devicePlatformType", default="") or "").casefold()
    non_game_terms = (
        "account management",
        "app auth",
        "customer support",
        "forums",
        "marketing site",
        "overlay",
        "onlineuser service",
        "shell client",
        "store",
        "twitch drops",
        "ubi.com",
        "ubiconnect",
        "uplay client",
        "webauth",
    )
    if any(term in title for term in non_game_terms):
        return True
    return platform in {"web", "webmarketing", "server"}


def _ubisoft_detail_game(app: dict[str, Any], details: dict[str, Any]) -> ImportedGame | None:
    app_id = _first(app, "applicationId", "appId", "id") or _first(details, "applicationId", "appId", "id")
    if not app_id or _ubisoft_is_non_game(details):
        return None
    title = _first(details, "displayName", "name", default=None) or _first(app, "name", "title", "displayName", "applicationName", default=f"Ubisoft App {app_id}")
    images = details.get("images") if isinstance(details.get("images"), dict) else {}
    return ImportedGame(
        platform_game_id=str(app_id),
        title=str(title),
        description=str(_first(details, "description", default="") or f"Ubisoft application id: {app_id}"),
        cover_url=_first(images, "highBoxArt", "lowBoxArt", "highThumbnail", "lowThumbnail", "background"),
        genres=_as_list(_first(details, "genre", "genres")),
        multiplayer=True,
        min_players=1,
        max_players=1,
        feature_metadata_known=False,
    )


def _ubisoft_games_from_applications(payload: Any, client: httpx.Client | None = None) -> list[ImportedGame]:
    if not isinstance(payload, dict) or not isinstance(payload.get("applications"), list):
        return []
    games: list[ImportedGame] = []
    seen: set[str] = set()
    for item in payload["applications"]:
        if not isinstance(item, dict):
            continue
        app_id = _first(item, "applicationId", "appId", "id")
        if not app_id or str(app_id) in seen:
            continue
        seen.add(str(app_id))
        details: dict[str, Any] = {}
        if client:
            try:
                response = client.get(f"https://public-ubiservices.ubi.com/v2/applications/{app_id}")
                if response.is_success and isinstance(response.json(), dict):
                    details = response.json()
            except Exception:
                details = {}
        game = _ubisoft_detail_game(item, details or item)
        if game:
            games.append(game)
    return games


def _ubisoft_pc_platform_types(game: dict[str, Any]) -> set[str]:
    viewer = game.get("viewer") if isinstance(game.get("viewer"), dict) else {}
    meta = viewer.get("meta") if isinstance(viewer.get("meta"), dict) else {}
    platform_groups = meta.get("ownedPlatformGroups") if isinstance(meta.get("ownedPlatformGroups"), list) else []
    platform_types: set[str] = set()
    for group in platform_groups:
        candidates = group if isinstance(group, list) else [group]
        for item in candidates:
            if isinstance(item, dict):
                platform_type = str(item.get("type") or "").strip().casefold()
                if platform_type:
                    platform_types.add(platform_type)
    return platform_types


def _ubisoft_games_from_club_graphql(payload: Any) -> list[ImportedGame]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    viewer = data.get("viewer") if isinstance(data.get("viewer"), dict) else {}
    owned_games = viewer.get("ownedGames") if isinstance(viewer.get("ownedGames"), dict) else {}
    nodes = owned_games.get("nodes") if isinstance(owned_games.get("nodes"), list) else []
    games: list[ImportedGame] = []
    seen: set[str] = set()
    for item in nodes:
        if not isinstance(item, dict) or "pc" not in _ubisoft_pc_platform_types(item):
            continue
        platform_id = str(_first(item, "spaceId", "id", default="") or "").strip()
        title = str(_first(item, "name", "title", "displayName", default="") or "").strip()
        if not platform_id or not title or platform_id in seen:
            continue
        seen.add(platform_id)
        games.append(
            ImportedGame(
                platform_game_id=platform_id,
                title=title,
                description=f"Ubisoft space id: {platform_id}",
                feature_metadata_known=False,
                player_count_known=False,
            )
        )
    return games


def _dedupe_imported_games(games: list[ImportedGame]) -> list[ImportedGame]:
    result: list[ImportedGame] = []
    seen: set[tuple[str, str]] = set()
    for game in games:
        key = (
            platform_value(game.mapping_platform or game.ownership_platform or Platform.ubisoft),
            game.platform_game_id,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(game)
    return result


def gog_auth_config_path(account_id: int) -> Path:
    return provider_auth_dir(Platform.gog, account_id) / "auth.json"


def legendary_env_for_account(account: Account) -> dict[str, str]:
    env = dict(os.environ)
    env["LEGENDARY_CONFIG_PATH"] = str(provider_auth_dir(account.platform, account.id))
    return env


def run_legendary_for_account(account: Account, args: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    command = settings.legendary_command or "legendary"
    try:
        return subprocess.run(
            [command, *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=legendary_env_for_account(account),
        )
    except FileNotFoundError as exc:
        raise RuntimeError("Legendary is not installed in the backend image.") from exc


@dataclass
class ImportedGame:
    platform_game_id: str
    title: str
    mapping_platform: Platform | None = None
    ownership_platform: Platform | None = None
    playtime_minutes: int = 0
    owned_since: datetime | None = None
    owned_since_source: str | None = None
    description: str = ""
    cover_url: str | None = None
    release_date: date | None = None
    genres: list[str] = field(default_factory=list)
    is_free: bool | None = None
    singleplayer: bool = False
    multiplayer: bool = False
    lan: bool = False
    local_coop: bool = False
    online_coop: bool = False
    hotseat: bool = False
    split_screen: bool = False
    shared_screen: bool = False
    min_players: int = 1
    max_players: int = 1
    feature_metadata_known: bool = False
    player_count_known: bool = False

    @property
    def normalized_title(self) -> str:
        return normalize_title(self.title)


@dataclass
class ImportBatch:
    games: list[ImportedGame]
    warnings: list[str] = field(default_factory=list)
    authoritative_snapshot: bool = True


class ImportProvider(Protocol):
    platform: Platform

    def sync_account(self, account: Account) -> list[ImportedGame] | ImportBatch:
        ...


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        timestamp = float(value)
        # BSON dates use milliseconds; tolerate microseconds from other importers too.
        while abs(timestamp) > 32_503_680_000:
            timestamp /= 1000
        try:
            parsed = datetime.fromtimestamp(timestamp)
        except (OverflowError, OSError, ValueError):
            return None
        if not 1970 <= parsed.year <= 2200:
            return None
        return parsed
    text = str(value).strip()
    for suffix in ("Z", "+00:00"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _parse_date(value: Any) -> date | None:
    parsed = _parse_datetime(value)
    if parsed:
        return parsed.date()
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().casefold() in {"1", "true", "yes", "y", "ja", "on"}


def _as_int(value: Any, default: int = 0) -> int:
    if value in (None, ""):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _as_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).replace(";", ",").split(",") if item.strip()]


def _first(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return default


def _flatten_candidate(item: dict[str, Any]) -> dict[str, Any]:
    flattened = dict(item)
    for nested_key in ("game", "libraryItem", "library_item", "details", "metadata", "product", "extra"):
        nested = flattened.get(nested_key)
        if isinstance(nested, dict):
            for key, value in nested.items():
                flattened.setdefault(key, value)
    return flattened


def _game_from_mapping(data: dict[str, Any], fallback_platform_id: str | None = None) -> ImportedGame | None:
    data = _flatten_candidate(data)
    title = _first(
        data,
        "title",
        "name",
        "app_name",
        "appTitle",
        "app_title",
        "product_title",
        "displayName",
        "display_name",
        "gameTitle",
        "game_name",
    )
    if not title:
        return None
    platform_game_id = str(
        _first(
            data,
            "platform_game_id",
            "platformGameId",
            "id",
            "titleId",
            "title_id",
            "app_id",
            "appId",
            "appName",
            "app_name",
            "product_id",
            "productId",
            "game_id",
            "gameId",
            default=fallback_platform_id or title,
        )
    )
    playtime = _as_int(_first(data, "playtime_minutes", "playtimeMinutes", "playtime", "minutes_played", "timePlayed", default=0))
    if "playtime_hours" in data:
        playtime = _as_int(float(data["playtime_hours"]) * 60)
    if "playtime_seconds" in data:
        playtime = _as_int(float(data["playtime_seconds"]) / 60)
    raw_min_players = _first(data, "min_players", "minPlayers", default=None)
    raw_max_players = _first(data, "max_players", "maxPlayers", default=None)
    return ImportedGame(
        platform_game_id=platform_game_id,
        title=str(title),
        playtime_minutes=playtime,
        owned_since=_parse_datetime(_first(data, "owned_since", "ownedSince", "date_purchased", "purchase_date", "purchaseDate")),
        description=str(_first(data, "description", "summary", default="") or ""),
        cover_url=_first(data, "cover_url", "coverUrl", "cover", "image", "keyImage", "icon", "boxArt"),
        release_date=_parse_date(_first(data, "release_date", "releaseDate", "released", "launchDate")),
        genres=_as_list(_first(data, "genres", "genre", "tags")),
        singleplayer=_as_bool(_first(data, "singleplayer", default=False)),
        multiplayer=_as_bool(_first(data, "multiplayer", default=False)),
        lan=_as_bool(_first(data, "lan", default=False)),
        local_coop=_as_bool(_first(data, "local_coop", "localCoop", default=False)),
        online_coop=_as_bool(_first(data, "online_coop", "onlineCoop", default=False)),
        hotseat=_as_bool(_first(data, "hotseat", default=False)),
        split_screen=_as_bool(_first(data, "split_screen", "splitScreen", default=False)),
        shared_screen=_as_bool(_first(data, "shared_screen", "sharedScreen", default=False)),
        min_players=max(1, _as_int(raw_min_players, 1)),
        max_players=max(1, _as_int(raw_max_players, 1)),
        feature_metadata_known=_as_bool(_first(data, "feature_metadata_known", "featureMetadataKnown", default=False)),
        player_count_known=_as_bool(
            _first(
                data,
                "player_count_known",
                "playerCountKnown",
                default=raw_min_players is not None or raw_max_players is not None,
            )
        ),
    )




def _steam_category_ids(details: dict[str, Any]) -> set[int]:
    ids: set[int] = set()
    for item in details.get("categories", []):
        if not isinstance(item, dict):
            continue
        try:
            ids.add(int(item.get("id")))
        except (TypeError, ValueError):
            continue
    return ids


def _steam_metadata_from_details(appid: int, details: dict[str, Any]) -> dict[str, Any]:
    category_ids = _steam_category_ids(details)
    categories = {str(item.get("description", "")).casefold() for item in details.get("categories", []) if isinstance(item, dict)}
    genres = [str(item.get("description")) for item in details.get("genres", []) if isinstance(item, dict) and item.get("description")]
    multiplayer = bool(category_ids & {1, 36, 37, 48, 49}) or any("multi-player" in category or "multiplayer" in category for category in categories)
    lan = bool(category_ids & {47, 48})
    local_coop = 24 in category_ids or 39 in category_ids
    online_coop = 38 in category_ids or 9 in category_ids
    split_screen = bool(category_ids & {24, 37, 39})
    shared_screen = bool(category_ids & {24, 37, 39})
    if local_coop or online_coop:
        multiplayer = True
    return {
        "description": str(details.get("short_description") or ""),
        "cover_url": details.get("header_image") or f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg",
        "release_date": _parse_date((details.get("release_date") or {}).get("date") if isinstance(details.get("release_date"), dict) else None),
        "genres": genres,
        "store_type": str(details.get("type") or "").casefold() or None,
        "is_free": bool(details.get("is_free")) and details.get("type") == "game",
        "singleplayer": 2 in category_ids or any("single-player" in category for category in categories),
        "multiplayer": multiplayer,
        "lan": lan,
        "local_coop": local_coop,
        "online_coop": online_coop,
        "split_screen": split_screen,
        "shared_screen": shared_screen,
        "min_players": 1,
        "max_players": 1,
        "feature_metadata_known": True,
        "player_count_known": False,
    }


def _merge_dicts(*payloads: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for payload in payloads:
        for key, value in payload.items():
            if value not in (None, ""):
                merged.setdefault(key, value)
    return merged


class SteamProvider:
    platform = Platform.steam
    authoritative_library = True

    def sync_account(self, account: Account) -> list[ImportedGame] | ImportBatch:
        warnings: list[str] = []
        authenticated_games: list[dict[str, Any]] | None = None
        try:
            authenticated_games = load_authenticated_steam_library(account.id, account.account_id)
        except Exception as exc:
            warnings.append(f"Gespeicherte Steam-Anmeldung konnte nicht verwendet werden: {exc}")

        api_games: list[dict[str, Any]] | None = None
        if settings.steam_api_key:
            try:
                url = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/"
                params = {
                    "key": settings.steam_api_key,
                    "steamid": account.account_id,
                    "include_appinfo": 1,
                    "include_played_free_games": 1,
                    "format": "json",
                }
                with httpx.Client(timeout=20) as client:
                    response = client.get(url, params=params)
                    response.raise_for_status()
                    steam_library = response.json().get("response")
                if not isinstance(steam_library, dict) or "game_count" not in steam_library:
                    raise RuntimeError("Die öffentliche Steam-Bibliothek ist nicht lesbar.")
                api_games = [item for item in steam_library.get("games") or [] if isinstance(item, dict)]
            except Exception as exc:
                warnings.append(f"Steam Web API konnte Spielzeiten nicht ergänzen: {exc}")
        elif authenticated_games is None:
            raise RuntimeError("STEAM_API_KEY is not configured and no Steam login is stored")

        if authenticated_games is None and api_games is None:
            raise RuntimeError("; ".join(warnings) or "Steam hat keine Spielebibliothek geliefert.")

        games_by_appid: dict[int, dict[str, Any]] = {}
        for item in authenticated_games or []:
            try:
                appid = int(item.get("appid"))
            except (TypeError, ValueError):
                continue
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            games_by_appid[appid] = {
                "appid": appid,
                "name": title,
                "playtime_forever": 0,
                "owned_since": item.get("owned_since"),
            }
        for item in api_games or []:
            try:
                appid = int(item.get("appid"))
            except (TypeError, ValueError):
                continue
            previous = games_by_appid.get(appid, {})
            games_by_appid[appid] = {**previous, **item, "owned_since": previous.get("owned_since")}
        games = list(games_by_appid.values())

        details_by_appid = self._load_store_metadata(games)
        imported_games: list[ImportedGame] = []
        for item in games:
            appid = int(item["appid"])
            metadata = details_by_appid.get(appid, {})
            if _is_non_game_steam_entry(str(item.get("name") or ""), metadata):
                continue
            imported_games.append(
                ImportedGame(
                    platform_game_id=str(appid),
                    title=item.get("name") or f"Steam App {appid}",
                    playtime_minutes=int(item.get("playtime_forever") or 0),
                    owned_since=_parse_datetime(item.get("owned_since")),
                    owned_since_source="steam_license" if item.get("owned_since") else None,
                    description=metadata.get("description", ""),
                    cover_url=metadata.get("cover_url") or f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg",
                    release_date=metadata.get("release_date"),
                    genres=metadata.get("genres", []),
                    is_free=metadata.get("is_free"),
                    singleplayer=metadata.get("singleplayer", False),
                    multiplayer=metadata.get("multiplayer", False),
                    lan=metadata.get("lan", False),
                    local_coop=metadata.get("local_coop", False),
                    online_coop=metadata.get("online_coop", False),
                    split_screen=metadata.get("split_screen", False),
                    shared_screen=metadata.get("shared_screen", False),
                    min_players=metadata.get("min_players", 1),
                    max_players=metadata.get("max_players", 1),
                    feature_metadata_known=metadata.get("feature_metadata_known", False),
                    player_count_known=metadata.get("player_count_known", False),
                )
            )
        if warnings:
            return ImportBatch(games=imported_games, warnings=warnings, authoritative_snapshot=True)
        return imported_games

    def _load_store_metadata(self, games: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
        limit = max(0, int(settings.steam_metadata_limit or 0))
        if limit == 0:
            return {}
        candidates = sorted(games, key=lambda item: str(item.get("name") or "").casefold())[:limit]
        appids = [int(item["appid"]) for item in candidates if item.get("appid")]
        details_by_appid: dict[int, dict[str, Any]] = {}
        timeout_seconds = float(settings.steam_store_timeout_seconds or 5.0)
        deadline = time.monotonic() + float(settings.steam_metadata_budget_seconds or 45.0)
        workers = max(1, int(settings.steam_metadata_workers or 8))

        def load_one(appid: int) -> tuple[int, dict[str, Any] | None]:
            if time.monotonic() >= deadline:
                return appid, None
            try:
                with httpx.Client(timeout=httpx.Timeout(timeout_seconds, connect=2.0)) as client:
                    response = client.get(
                        "https://store.steampowered.com/api/appdetails",
                        params={"appids": str(appid), "filters": "basic,categories,genres,release_date"},
                        headers={"User-Agent": f"Mozilla/5.0 ({settings.app_client_identifier})"},
                    )
                    response.raise_for_status()
                    payload = response.json()
                    item = payload.get(str(appid), {}) if isinstance(payload, dict) else {}
                    if isinstance(item, dict) and item.get("success") and isinstance(item.get("data"), dict):
                        return appid, _steam_metadata_from_details(appid, item["data"])
            except Exception:
                return appid, None
            return appid, None

        executor = ThreadPoolExecutor(max_workers=workers)
        futures = [executor.submit(load_one, appid) for appid in appids]
        try:
            for future in as_completed(futures, timeout=max(1.0, float(settings.steam_metadata_budget_seconds or 45.0))):
                if time.monotonic() >= deadline:
                    break
                try:
                    appid, metadata = future.result(timeout=0)
                except Exception:
                    continue
                if metadata:
                    details_by_appid[appid] = metadata
        except TimeoutError:
            pass
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        return details_by_appid


def _is_non_game_steam_entry(title: str, metadata: dict[str, Any]) -> bool:
    return classify_game(
        title,
        metadata.get("genres") or [],
        store_type=metadata.get("store_type"),
    ).is_game is False


class EpicProvider:
    platform = Platform.epic
    authoritative_library = True

    @staticmethod
    def _is_game(item: dict[str, Any]) -> bool:
        metadata = item.get("metadata")
        categories = metadata.get("categories") if isinstance(metadata, dict) else []
        category_paths = {
            str(category.get("path") or "").casefold()
            for category in categories or []
            if isinstance(category, dict)
        }
        return "digitalextras" not in category_paths

    def sync_account(self, account: Account) -> list[ImportedGame]:
        if is_placeholder_display_name(account):
            status_result = run_legendary_for_account(account, ["status", "--json"], timeout=30)
            if status_result.returncode == 0:
                try:
                    status_payload = json.loads(status_result.stdout or "{}")
                except json.JSONDecodeError:
                    status_payload = {}
                if isinstance(status_payload, dict) and status_payload.get("account"):
                    apply_account_identity(
                        account,
                        {"provider_display_name": status_payload["account"]},
                    )
        result = run_legendary_for_account(account, ["list", "--json"], timeout=120)
        if result.returncode != 0:
            output = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"Legendary failed for Epic sync: {output or result.returncode}")

        payload = json.loads(result.stdout or "[]")
        items = payload.get("games") if isinstance(payload, dict) and isinstance(payload.get("games"), list) else payload
        if not isinstance(items, list):
            raise RuntimeError("Legendary returned an unexpected JSON shape")

        games: list[ImportedGame] = []
        for item in items:
            if isinstance(item, dict) and self._is_game(item):
                data = _flatten_candidate(item)
                title = _first(data, "app_title", "title", "name", "appName", "displayName")
                if not title:
                    continue
                games.append(
                    ImportedGame(
                        platform_game_id=str(_first(data, "app_name", "appName", "id", default=title)),
                        title=str(title),
                        playtime_minutes=_as_int(_first(data, "playtime_minutes", "playtime", "minutes_played", default=0)),
                        description=str(_first(data, "description", default="") or ""),
                        cover_url=_first(data, "cover_url", "cover", "image", "boxArt"),
                        release_date=_parse_date(_first(data, "release_date", "releaseDate")),
                        genres=_as_list(_first(data, "genres", "genre", "tags")),
                        singleplayer=_as_bool(_first(data, "singleplayer", default=False)),
                        multiplayer=_as_bool(_first(data, "multiplayer", default=False)),
                        lan=_as_bool(_first(data, "lan", default=False)),
                        local_coop=_as_bool(_first(data, "local_coop", "localCoop", default=False)),
                        online_coop=_as_bool(_first(data, "online_coop", "onlineCoop", default=False)),
                        hotseat=_as_bool(_first(data, "hotseat", default=False)),
                        split_screen=_as_bool(_first(data, "split_screen", "splitScreen", default=False)),
                        shared_screen=_as_bool(_first(data, "shared_screen", "sharedScreen", default=False)),
                        min_players=max(1, _as_int(_first(data, "min_players", "minPlayers", default=1), 1)),
                        max_players=max(1, _as_int(_first(data, "max_players", "maxPlayers", default=1), 1)),
                    )
                )
        return games


class GOGAuthStore:
    def __init__(self, config_path: str | None = None) -> None:
        self.config_path = Path(config_path) if config_path else GOG_DEFAULT_CACHE

    def _load_all(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {}
        return json.loads(self.config_path.read_text(encoding="utf-8"))

    def _save_all(self, payload: dict[str, Any]) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        write_private_json(self.config_path, payload)

    def get_credentials(self) -> dict[str, Any]:
        all_credentials = self._load_all()
        credentials = all_credentials.get(GOG_CLIENT_ID)
        if not credentials:
            raise RuntimeError(
                f"No GOG auth cache found at {self.config_path}. Authenticate GOG once and keep the cache mounted."
            )
        if self.is_expired(credentials):
            credentials = self.refresh_credentials(all_credentials, credentials)
        return credentials

    def is_expired(self, credentials: dict[str, Any]) -> bool:
        login_time = credentials.get("loginTime")
        expires_in = credentials.get("expires_in")
        if login_time is None or expires_in is None:
            return True
        return time.time() >= float(login_time) + float(expires_in)

    def refresh_credentials(self, all_credentials: dict[str, Any], credentials: dict[str, Any]) -> dict[str, Any]:
        refresh_token = credentials.get("refresh_token")
        if not refresh_token:
            raise RuntimeError("GOG auth cache does not contain a refresh token")
        params = {
            "client_id": GOG_CLIENT_ID,
            "client_secret": GOG_CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "without_new_session": 1,
        }
        response = httpx.get(GOG_AUTH_URL, params=params, timeout=20)
        response.raise_for_status()
        refreshed = response.json()
        refreshed["loginTime"] = time.time()
        all_credentials[GOG_CLIENT_ID] = refreshed
        self._save_all(all_credentials)
        return refreshed


class GOGProvider:
    platform = Platform.gog
    authoritative_library = True

    def sync_account(self, account: Account) -> list[ImportedGame] | ImportBatch:
        credentials = GOGAuthStore(str(gog_auth_config_path(account.id))).get_credentials()
        token = credentials.get("access_token")
        if not token:
            raise RuntimeError("GOG auth cache is missing an access token")
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": f"gogdl/0 ({settings.app_client_identifier})",
            "Accept-Language": "en-US",
        }
        with httpx.Client(headers=headers, timeout=30) as client:
            if is_placeholder_display_name(account):
                try:
                    profile_response = client.get(f"{GOG_EMBED_URL}/userData.json")
                    if profile_response.is_success:
                        profile = profile_response.json()
                        if isinstance(profile, dict):
                            apply_account_identity(
                                account,
                                {
                                    "provider_display_name": _first(
                                        profile,
                                        "username",
                                        "displayName",
                                        "display_name",
                                        default=None,
                                    ),
                                    "provider_account_id": _first(
                                        profile,
                                        "userId",
                                        "user_id",
                                        "accountId",
                                        "account_id",
                                        default=credentials.get("user_id"),
                                    ),
                                },
                            )
                except Exception:
                    pass
            owned_response = client.get(f"{GOG_EMBED_URL}/user/data/games")
            owned_response.raise_for_status()
            owned_ids = owned_response.json().get("owned", [])
            results: list[ImportedGame] = []
            warnings: list[str] = []
            for game_id in owned_ids:
                try:
                    product_response = client.get(f"{GOG_API_URL}/products/{game_id}")
                    product_payload = product_response.json() if product_response.is_success else {}
                    product_data = product_payload if isinstance(product_payload, dict) else {}
                    details_response = client.get(f"{GOG_EMBED_URL}/account/gameDetails/{game_id}.json")
                    details_payload = details_response.json() if details_response.is_success else {}
                    details_data = details_payload if isinstance(details_payload, dict) else {}
                    data = _merge_dicts({"platform_game_id": str(game_id)}, product_data, details_data)
                    title = _resolved_gog_title(product_data, details_data)
                    if not title:
                        raise ValueError("GOG lieferte nur einen internen Titelplatzhalter")
                    data["title"] = title
                    game = _game_from_mapping(data, fallback_platform_id=str(game_id))
                    if not game:
                        raise ValueError("GOG-Produkt konnte nicht in ein Spiel umgewandelt werden")
                    if game.owned_since:
                        game.owned_since_source = "gog_entitlement"
                    results.append(game)
                except Exception as exc:
                    warning = f"GOG-Produkt {game_id} wurde übersprungen: {exc}"
                    warnings.append(warning)
                    LOGGER.warning(warning)
            if warnings and owned_ids and not results:
                raise RuntimeError(
                    f"Keines der {len(owned_ids)} GOG-Produkte konnte verarbeitet werden; "
                    "die bestehende Bibliothek wurde unverändert beibehalten. "
                    + " | ".join(warnings[:3])
                )
            return ImportBatch(
                games=results,
                warnings=warnings,
                authoritative_snapshot=not warnings,
            )


GOG_TITLE_TOKEN = re.compile(r"^product_title_\d+$", re.IGNORECASE)


def _resolved_gog_title(
    product_data: dict[str, Any],
    details_data: dict[str, Any],
) -> str | None:
    for payload in (product_data, details_data):
        value = _first(
            payload,
            "title",
            "name",
            "productTitle",
            "product_title",
            default=None,
        )
        title = str(value or "").strip()
        if title and not GOG_TITLE_TOKEN.fullmatch(title):
            return title
    return None


UBISOFT_APP_ID = settings.ubisoft_app_id
UBISOFT_CLUB_GRAPHQL_URL = settings.ubisoft_club_graphql_url
UBISOFT_CLUB_OWNED_GAMES_QUERY = """
query AllGames {
  viewer {
    id
    ownedGames: games(filterBy: {isOwned: true}) {
      totalCount
      nodes {
        id
        spaceId
        name
        viewer {
          meta {
            id
            ownedPlatformGroups {
              id
              name
              type
            }
          }
        }
      }
    }
  }
}
""".strip()


class UbisoftProvider:
    platform = Platform.ubisoft

    def sync_account(self, account: Account) -> list[ImportedGame]:
        credentials = load_provider_auth_json(Platform.ubisoft, account.id)
        if is_placeholder_display_name(account):
            apply_account_identity(
                account,
                {
                    "provider_display_name": _first(
                        credentials,
                        "nameOnPlatform",
                        "username",
                        "displayName",
                        "display_name",
                        default=None,
                    ),
                    "provider_account_id": _first(
                        credentials,
                        "profileId",
                        "profile_id",
                        "userId",
                        "user_id",
                        "accountId",
                        "account_id",
                        default=None,
                    ),
                },
            )
        ticket = credentials.get("ticket") or credentials.get("access_token") or credentials.get("accessToken")
        profile_id = credentials.get("profileId") or credentials.get("profile_id") or credentials.get("userId") or credentials.get("user_id") or credentials.get("accountId") or credentials.get("account_id") or account.account_id
        if not ticket or not profile_id:
            raise RuntimeError("Ubisoft auth needs ticket and profileId")
        headers = {
            "Authorization": f"Ubi_v1 t={ticket}",
            "Ubi-AppId": str(credentials.get("appId") or UBISOFT_APP_ID),
            "User-Agent": f"UbisoftConnect/1.0 {settings.app_client_identifier}",
        }
        if credentials.get("sessionId"):
            headers["Ubi-SessionId"] = str(credentials["sessionId"])
        urls = [
            f"https://public-ubiservices.ubi.com/v3/profiles/{profile_id}/applications?locale=en-US&limit=100",
            f"https://public-ubiservices.ubi.com/v1/profiles/{profile_id}/applications?locale=en-US&limit=100",
            f"https://public-ubiservices.ubi.com/v1/profiles/{profile_id}/games?locale=en-US",
            f"https://public-ubiservices.ubi.com/v2/profiles/{profile_id}/games?locale=en-US",
            f"https://public-ubiservices.ubi.com/v1/users/{profile_id}/entitlements",
        ]
        errors: list[str] = []
        imported_games: list[ImportedGame] = []
        with httpx.Client(headers=headers, timeout=30) as client:
            try:
                response = client.post(
                    UBISOFT_CLUB_GRAPHQL_URL,
                    json={
                        "operationName": "AllGames",
                        "variables": {"owned": True},
                        "query": UBISOFT_CLUB_OWNED_GAMES_QUERY,
                    },
                    headers={"Content-Type": "application/json"},
                )
                if response.is_success:
                    games = _ubisoft_games_from_club_graphql(response.json())
                    if games:
                        imported_games.extend(games)
                    else:
                        errors.append(f"{UBISOFT_CLUB_GRAPHQL_URL}: no PC games found")
                else:
                    errors.append(f"{UBISOFT_CLUB_GRAPHQL_URL}: {response.status_code}")
            except Exception as exc:
                errors.append(f"{UBISOFT_CLUB_GRAPHQL_URL}: {exc.__class__.__name__}")

            for url in urls:
                response = client.get(url)
                if response.is_success:
                    payload = response.json()
                    games = _ubisoft_games_from_applications(payload, client) or _games_from_payload(payload, "ubisoft")
                    if games:
                        imported_games.extend(games)
                        continue
                    errors.append(f"{url}: no games found")
                else:
                    errors.append(f"{url}: {response.status_code}")
        if imported_games:
            return _dedupe_imported_games(imported_games)
        raise RuntimeError("Ubisoft sync did not return a library: " + "; ".join(errors[-3:]))


class XboxProvider:
    platform = Platform.xbox

    def sync_account(self, account: Account) -> list[ImportedGame]:
        from app.services.xbox_auth import ensure_xbox_credentials

        credentials = ensure_xbox_credentials(account)
        xsts_token = credentials.get("xsts_token") or credentials.get("Token")
        user_hash = credentials.get("user_hash") or credentials.get("uhs")
        xuid = credentials.get("xuid") or credentials.get("userXuid") or account.account_id
        if not xsts_token or not user_hash or not xuid:
            raise RuntimeError("Xbox auth needs xsts_token, user_hash and xuid")
        headers = {
            "Authorization": f"XBL3.0 x={user_hash};{xsts_token}",
            "x-xbl-contract-version": "2",
            "Accept-Language": "en-US",
        }
        url = f"https://titlehub.xboxlive.com/users/xuid({xuid})/titles/titlehistory/decoration/detail,scid,image"
        response = httpx.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        games = _xbox_pc_games_from_payload(response.json())
        if not games:
            raise RuntimeError("Xbox title history returned no PC games")
        return games


def _ea_owned_games_container(data: dict[str, Any]) -> dict[str, Any]:
    me = data.get("me")
    if not isinstance(me, dict):
        return {}
    for key in ("ownedGameProducts", "preloadedOwnedGames", "ownedGames"):
        value = me.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _ea_product_image(product: dict[str, Any]) -> str | None:
    for path in (
        ("packArt", "large"),
        ("packArt", "medium"),
        ("image", "url"),
        ("keyArt", "url"),
        ("heroImage", "url"),
    ):
        value: Any = product
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
    return None


def _ea_genres(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        name = item.get("name") if isinstance(item, dict) else item
        if name:
            result.append(str(name))
    return result


def _ea_imported_game(item: dict[str, Any]) -> tuple[ImportedGame, str | None] | None:
    product = item.get("product")
    if not isinstance(product, dict):
        product = item
    title = product.get("name") or product.get("title") or item.get("name")
    product_id = (
        item.get("originOfferId")
        or item.get("offerId")
        or item.get("entitlementId")
        or product.get("offerId")
        or product.get("id")
    )
    if not title or not product_id:
        return None
    game_slug = product.get("gameSlug") or item.get("gameSlug")
    product_user = product.get("gameProductUser")
    if not isinstance(product_user, dict):
        product_user = {}
    owned_since = _parse_datetime(
        product_user.get("initialEntitlementDate")
        or item.get("initialEntitlementDate")
        or item.get("entitlementDate")
    )
    game = ImportedGame(
        platform_game_id=str(product_id),
        title=str(title).strip(),
        playtime_minutes=0,
        owned_since=owned_since,
        owned_since_source="ea_entitlement" if owned_since else None,
        description=str(product.get("shortDescription") or product.get("description") or ""),
        cover_url=_ea_product_image(product),
        release_date=_parse_date(product.get("releaseDate") or product.get("releaseDateTime")),
        genres=_ea_genres(product.get("genres")),
    )
    return game, str(game_slug) if game_slug else None


def _ea_play_times(data: dict[str, Any]) -> dict[str, tuple[int, datetime | None]]:
    result: dict[str, tuple[int, datetime | None]] = {}

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            slug = value.get("gameSlug")
            seconds = value.get("totalPlayTimeSeconds")
            if slug and seconds is not None:
                try:
                    minutes = max(0, int(float(seconds) // 60))
                except (TypeError, ValueError):
                    minutes = 0
                result[str(slug)] = (minutes, _parse_datetime(value.get("lastSessionEndDate")))
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(data)
    return result


def _ea_response_json(response: httpx.Response, operation_name: str) -> dict[str, Any]:
    if response.status_code in {401, 403}:
        raise RuntimeError("Die EA-Anmeldung ist abgelaufen. Bitte EA erneut verbinden.")
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"EA {operation_name} hat keine verwertbaren Daten geliefert.")
    return payload


def _ea_origin_user_id(client: httpx.Client) -> str:
    payload = _ea_response_json(client.get(EA_IDENTITY_URL), "Origin-Identitätsabfrage")
    pid = payload.get("pid") if isinstance(payload.get("pid"), dict) else {}
    user_id = pid.get("pidId") or pid.get("id")
    if not user_id:
        raise RuntimeError("EA Origin-Identitätsabfrage lieferte keine User-ID.")
    return str(user_id)


def _ea_origin_entitlements(client: httpx.Client, user_id: str) -> tuple[str, list[dict[str, Any]]]:
    errors: list[str] = []
    for base_url in EA_ORIGIN_API_BASE_URLS:
        url = f"{base_url}/ecommerce2/consolidatedentitlements/{quote(user_id, safe='')}?machine_hash=1"
        try:
            payload = _ea_response_json(client.get(url), "Origin-Entitlements")
        except (httpx.HTTPError, RuntimeError, ValueError) as exc:
            errors.append(f"{base_url}: {exc}")
            continue
        entitlements = payload.get("entitlements")
        if isinstance(entitlements, list):
            return base_url, [item for item in entitlements if isinstance(item, dict)]
        errors.append(f"{base_url}: keine Entitlement-Liste")
    raise RuntimeError("; ".join(errors) or "EA Origin-Entitlements nicht erreichbar.")


def _ea_origin_offer(client: httpx.Client, base_url: str, offer_id: str) -> dict[str, Any]:
    url = f"{base_url}/ecommerce2/public/supercat/{quote(offer_id, safe=':.')}/en_US"
    return _ea_response_json(client.get(url), "Origin-Angebotsdetails")


def _ea_origin_imported_games(client: httpx.Client) -> list[ImportedGame]:
    user_id = _ea_origin_user_id(client)
    base_url, entitlements = _ea_origin_entitlements(client, user_id)
    games: list[ImportedGame] = []
    seen: set[str] = set()
    for entitlement in entitlements:
        if str(entitlement.get("offerType") or "").casefold() != "basegame":
            continue
        offer_id = str(entitlement.get("offerId") or "").strip()
        if not offer_id:
            continue
        external_type = str(entitlement.get("externalType") or "").strip().casefold()
        platform_id = f"{offer_id}@{external_type}" if external_type else offer_id
        if platform_id in seen:
            continue
        try:
            offer = _ea_origin_offer(client, base_url, offer_id)
        except (httpx.HTTPError, RuntimeError, ValueError):
            continue
        i18n = offer.get("i18n") if isinstance(offer.get("i18n"), dict) else {}
        title = str(i18n.get("displayName") or offer.get("displayName") or offer.get("name") or "").strip()
        if not title:
            continue
        seen.add(platform_id)
        grant_date = _parse_datetime(entitlement.get("grantDate"))
        games.append(
            ImportedGame(
                platform_game_id=platform_id,
                title=title,
                owned_since=grant_date,
                owned_since_source="ea_entitlement" if grant_date else None,
                description=str(i18n.get("longDescription") or i18n.get("shortDescription") or ""),
                cover_url=_ea_product_image(offer),
                release_date=_parse_date(offer.get("releaseDate") or offer.get("downloadStartDate")),
                feature_metadata_known=False,
            )
        )
    return games


class EAProvider:
    platform = Platform.ea
    authoritative_library = True

    def sync_account(self, account: Account) -> ImportBatch:
        credentials = load_provider_auth_json(Platform.ea, account.id)
        token = str(credentials.get("access_token") or "").strip()
        if not token:
            raise RuntimeError("EA ist nicht verbunden. Bitte den Account unter Accounts & Logins neu verbinden.")

        games_by_id: dict[str, ImportedGame] = {}
        slugs_by_id: dict[str, str] = {}
        warnings: list[str] = []
        offset = "0"
        seen_offsets: set[str] = set()
        page_size = 500
        received_items = 0
        declared_total: int | None = None
        unresolved_items = 0
        pagination_complete = True
        origin_fallback_added = 0

        with httpx.Client(headers=ea_request_headers(token), timeout=45) as client:
            while True:
                if offset in seen_offsets:
                    warnings.append(
                        "EA wiederholte denselben Bibliotheks-Cursor; die bereits gelesenen Spiele wurden übernommen, "
                        "bestehende EA-Besitzstände aber nicht gelöscht."
                    )
                    pagination_complete = False
                    break
                seen_offsets.add(offset)
                try:
                    response = client.get(ea_owned_games_url(offset=offset, limit=page_size))
                    data = _ea_graphql_data(response, "Bibliotheksabfrage")
                except (httpx.HTTPError, RuntimeError, ValueError) as exc:
                    if not games_by_id:
                        raise
                    warnings.append(
                        f"Eine EA-Bibliotheksseite konnte nicht geladen werden: {exc}. "
                        "Die bereits gelesenen Spiele wurden übernommen; bestehende EA-Besitzstände wurden nicht gelöscht."
                    )
                    pagination_complete = False
                    break
                container = _ea_owned_games_container(data)
                items = container.get("items")
                if not isinstance(items, list):
                    if not games_by_id:
                        raise RuntimeError(
                            "EA hat keine verwertbare Spieleliste zurückgegeben; vorhandene Daten bleiben erhalten."
                        )
                    warnings.append(
                        "Eine EA-Bibliotheksseite enthielt keine Spieleliste. Die bereits gelesenen Spiele wurden "
                        "übernommen; bestehende EA-Besitzstände wurden nicht gelöscht."
                    )
                    pagination_complete = False
                    break
                received_items += len(items)
                try:
                    declared_total = int(container.get("totalCount"))
                except (TypeError, ValueError):
                    pass
                for item in items:
                    parsed = _ea_imported_game(item) if isinstance(item, dict) else None
                    if not parsed:
                        unresolved_items += 1
                        continue
                    game, slug = parsed
                    games_by_id[game.platform_game_id] = game
                    if slug:
                        slugs_by_id[game.platform_game_id] = slug

                next_offset = container.get("next")
                if isinstance(next_offset, dict):
                    next_offset = next_offset.get("offset") or next_offset.get("cursor")
                if not next_offset:
                    break
                offset = str(next_offset)

            if declared_total is not None and received_items < declared_total:
                warnings.append(
                    f"EA meldete {declared_total} Einträge, lieferte für die gefilterte PC-Bibliothek aber "
                    f"{received_items}. Die gelieferten Spiele wurden übernommen; bestehende EA-Besitzstände "
                    "wurden nicht gelöscht."
                )
                pagination_complete = False
            slug_items = list(dict.fromkeys(slugs_by_id.values()))
            play_times: dict[str, tuple[int, datetime | None]] = {}
            for start in range(0, len(slug_items), 50):
                batch = slug_items[start : start + 50]
                url = _ea_graphql_url(
                    "GetGamePlayTimes",
                    {"gameSlugs": batch},
                    EA_PLAY_TIMES_QUERY_HASH,
                )
                try:
                    play_times.update(_ea_play_times(_ea_graphql_data(client.get(url), "Spielzeitabfrage")))
                except (httpx.HTTPError, RuntimeError, ValueError) as exc:
                    warnings.append(f"EA-Spielzeiten konnten teilweise nicht geladen werden: {exc}")
                    break

            try:
                for game in _ea_origin_imported_games(client):
                    if game.platform_game_id in games_by_id:
                        continue
                    games_by_id[game.platform_game_id] = game
                    origin_fallback_added += 1
            except Exception as exc:
                if not games_by_id or not pagination_complete:
                    warnings.append(f"EA-Origin-Fallback konnte nicht gelesen werden: {exc}")

        if not games_by_id and declared_total != 0:
            raise RuntimeError("EA hat keine Spielebibliothek zurückgegeben; vorhandene Daten bleiben erhalten.")
        if unresolved_items:
            warnings.append(
                f"{unresolved_items} EA-Bibliothekseinträge hatten keinen auflösbaren Titel oder keine Offer-ID; "
                "bestehende EA-Besitzstände wurden deshalb nicht gelöscht."
            )
        for product_id, slug in slugs_by_id.items():
            timing = play_times.get(slug)
            if not timing:
                continue
            games_by_id[product_id].playtime_minutes = timing[0]
        if origin_fallback_added:
            warnings.append(
                f"EA-Origin-Fallback ergänzte {origin_fallback_added} Spiele, die Juno nicht geliefert hat; "
                "bestehende EA-Besitzstände wurden deshalb nicht gelöscht."
            )
            pagination_complete = False
        return ImportBatch(
            games=list(games_by_id.values()),
            warnings=warnings,
            authoritative_snapshot=pagination_complete and unresolved_items == 0,
        )


def _amazon_credentials(account: Account) -> dict[str, Any]:
    credentials = load_provider_auth_json(Platform.amazon, account.id)
    access_token = credentials.get("access_token")
    expires_at = float(credentials.get("expires_at") or 0)
    if access_token and expires_at > time.time() + 60:
        return credentials
    refresh_token = credentials.get("refresh_token")
    if not refresh_token:
        raise RuntimeError("Amazon-Anmeldung ist abgelaufen. Bitte den Account neu verbinden.")
    response = httpx.post(
        AMAZON_TOKEN_URL,
        json={
            "app_name": "AGSLauncher for Windows",
            "app_version": "1.0.0",
            "source_token": refresh_token,
            "requested_token_type": "access_token",
            "source_token_type": "refresh_token",
        },
        headers={"User-Agent": "AGSLauncher/1.0.0"},
        timeout=30,
    )
    response.raise_for_status()
    refreshed = response.json()
    credentials.update(refreshed)
    credentials["expires_at"] = time.time() + float(refreshed.get("expires_in") or 3600)
    save_provider_auth_json(Platform.amazon, account.id, credentials)
    return credentials


class AmazonProvider:
    platform = Platform.amazon
    authoritative_library = True

    def sync_account(self, account: Account) -> list[ImportedGame]:
        credentials = _amazon_credentials(account)
        token = credentials.get("access_token")
        headers = {
            "User-Agent": "com.amazon.agslauncher.win/3.0.9495.3",
            "X-Amz-Target": "com.amazon.animusdistributionservice.entitlement.AnimusEntitlementsService.GetEntitlements",
            "x-amzn-token": str(token),
            "Content-Encoding": "amz-1.0",
            "Expect": "100-continue",
        }
        device_serial = str(credentials.get("device_serial") or "")
        if not device_serial:
            raise RuntimeError("Amazon-Gerätekennung fehlt. Bitte den Account neu verbinden.")
        request_data: dict[str, Any] = {
            "Operation": "GetEntitlements",
            "clientId": "Sonic",
            "syncPoint": None,
            "nextToken": None,
            "maxResults": 50,
            "productIdFilter": None,
            "keyId": "d5dc8b8b-86c8-4fc4-ae93-18c0def5314d",
            "hardwareHash": hashlib.sha256(device_serial.encode("utf-8")).hexdigest().upper(),
        }
        games: list[ImportedGame] = []
        with httpx.Client(headers=headers, timeout=40) as client:
            while True:
                response = client.post(AMAZON_ENTITLEMENTS_URL, json=request_data)
                response.raise_for_status()
                payload = response.json()
                for entitlement in payload.get("entitlements") or []:
                    product = entitlement.get("product") if isinstance(entitlement, dict) else None
                    if not isinstance(product, dict) or product.get("productLine") == "Twitch:FuelEntitlement":
                        continue
                    title = str(product.get("title") or "").strip()
                    product_id = str(product.get("id") or product.get("asin") or "").strip()
                    if not title or not product_id:
                        continue
                    detail = product.get("productDetail") if isinstance(product.get("productDetail"), dict) else {}
                    games.append(
                        ImportedGame(
                            platform_game_id=product_id,
                            title=title,
                            cover_url=detail.get("iconUrl"),
                            feature_metadata_known=False,
                        )
                    )
                next_token = payload.get("nextToken")
                if not next_token:
                    break
                request_data["nextToken"] = next_token
        if not games:
            raise RuntimeError("Amazon Games hat keine Bibliothek zurückgegeben; vorhandene Daten bleiben erhalten.")
        return games


class BattleNetProvider:
    platform = Platform.battle_net
    authoritative_library = True

    def sync_account(self, account: Account) -> list[ImportedGame]:
        credentials = load_provider_auth_json(Platform.battle_net, account.id)
        headers = _cookie_headers(credentials)
        games: list[ImportedGame] = []
        seen: set[str] = set()
        with httpx.Client(headers=headers, follow_redirects=True, timeout=30) as client:
            client.get("https://account.battle.net/oauth2/authorization/account-settings")
            status_response = client.get("https://account.battle.net/api/")
            if status_response.status_code == 401:
                raise RuntimeError("Battle.net-Sitzung ist abgelaufen. Bitte den Account neu verbinden.")
            games_response = client.get("https://account.battle.net/api/games-and-subs")
            games_response.raise_for_status()
            for item in games_response.json().get("gameAccounts") or []:
                title = str(item.get("localizedGameName") or "").strip()
                title_id = str(item.get("titleId") or "").strip()
                if not title or not title_id or title_id in seen:
                    continue
                seen.add(title_id)
                games.append(ImportedGame(platform_game_id=title_id, title=title, feature_metadata_known=False))
            classic_response = client.get("https://account.battle.net/api/classic-games")
            if classic_response.is_success:
                for index, item in enumerate(classic_response.json().get("classicGames") or []):
                    title = str(item.get("localizedGameName") or "").strip()
                    if not title:
                        continue
                    icon = str(item.get("regionalGameFranchiseIconFilename") or "")
                    platform_id = f"classic:{icon or normalize_title(title)}:{index}"
                    if platform_id not in seen:
                        seen.add(platform_id)
                        games.append(ImportedGame(platform_game_id=platform_id, title=title, feature_metadata_known=False))
        if not games:
            raise RuntimeError("Battle.net hat keine Spiele zurückgegeben; vorhandene Daten bleiben erhalten.")
        return games


class HumbleProvider:
    platform = Platform.humble
    authoritative_library = True
    authoritative_ownership_platforms = {Platform.humble_key}

    def sync_account(self, account: Account) -> list[ImportedGame]:
        credentials = load_provider_auth_json(Platform.humble, account.id)
        headers = _cookie_headers(credentials)
        with httpx.Client(headers=headers, follow_redirects=True, timeout=40) as client:
            orders_response = client.get("https://www.humblebundle.com/api/v1/user/order")
            orders_response.raise_for_status()
            if "application/json" not in str(orders_response.headers.get("content-type") or ""):
                raise RuntimeError("Humble-Sitzung ist abgelaufen. Bitte den Account neu verbinden.")
            order_refs = orders_response.json()
            if not isinstance(order_refs, list):
                raise RuntimeError("Humble hat eine unerwartete Bestellliste zurückgegeben; vorhandene Daten bleiben erhalten.")
            game_keys = [
                str(item.get("gamekey"))
                for item in order_refs
                if isinstance(item, dict) and item.get("gamekey")
            ]
            if not game_keys:
                raise RuntimeError("Humble hat keine Bibliothek zurückgegeben; vorhandene Daten bleiben erhalten.")
            games: list[ImportedGame] = []
            seen: set[str] = set()
            seen_key_titles: set[str] = set()
            for offset in range(0, len(game_keys), 40):
                params: list[tuple[str, str]] = [("all_tpkds", "true")]
                params.extend(("gamekeys", key) for key in game_keys[offset : offset + 40])
                response = client.get("https://www.humblebundle.com/api/v1/orders", params=params)
                response.raise_for_status()
                orders = response.json()
                order_values = orders.values() if isinstance(orders, dict) else []
                for order in order_values:
                    if not isinstance(order, dict):
                        continue
                    for product in order.get("subproducts") or []:
                        if not isinstance(product, dict):
                            continue
                        downloads = product.get("downloads") or []
                        if not any(isinstance(download, dict) and download.get("platform") == "windows" for download in downloads):
                            continue
                        title = str(product.get("human_name") or "").strip()
                        product_id = str(product.get("machine_name") or "").strip()
                        if not title or not product_id or product_id in seen:
                            continue
                        seen.add(product_id)
                        games.append(
                            ImportedGame(
                                platform_game_id=product_id,
                                title=title,
                                owned_since=_parse_datetime(order.get("created")),
                                owned_since_source="humble_order" if order.get("created") else None,
                                cover_url=product.get("icon"),
                                feature_metadata_known=False,
                            )
                        )
                    for key_entry in (order.get("tpkd_dict") or {}).get("all_tpks") or []:
                        key_game = _humble_available_key_game(order, key_entry)
                        key_title = normalize_title(key_game.title) if key_game else ""
                        if key_game and key_title not in seen_key_titles:
                            seen_key_titles.add(key_title)
                            games.append(key_game)
        if not games:
            raise RuntimeError("Humble hat keine Windows-Spiele zurückgegeben; vorhandene Daten bleiben erhalten.")
        return games


HUMBLE_GAME_KEY_TYPES = {
    "steam",
    "gog",
    "rockstar_social",
    "origin",
    "ea",
    "uplay",
    "ubisoft",
    "epic",
    "epic_games",
    "battle_net",
    "battlenet",
    "oculus",
    "meta",
}
HUMBLE_EXTERNAL_GAME_PROVIDERS = {
    "battle.net",
    "blizzard",
    "ea",
    "ea app",
    "epic games",
    "gog",
    "meta",
    "oculus",
    "origin",
    "rockstar",
    "steam",
    "ubisoft",
    "uplay",
}


def _humble_available_key_game(order: dict[str, Any], item: Any) -> ImportedGame | None:
    if not isinstance(item, dict):
        return None
    if "redeemed_key_val" in item:
        return None
    if item.get("is_expired") or item.get("sold_out") or not item.get("visible", True):
        return None
    key_type = str(item.get("key_type") or "").strip().casefold()
    provider = str(item.get("key_type_human_name") or "").strip().casefold()
    is_game_provider = key_type in HUMBLE_GAME_KEY_TYPES or (
        key_type == "external_key" and provider in HUMBLE_EXTERNAL_GAME_PROVIDERS
    )
    if not is_game_provider:
        return None
    title = str(item.get("human_name") or "").strip()
    if not title:
        return None
    order_id = str(order.get("gamekey") or "order")
    key_index = str(item.get("keyindex") if item.get("keyindex") is not None else "key")
    machine_name = str(item.get("machine_name") or normalize_title(title))
    return ImportedGame(
        platform_game_id=f"{order_id}:{key_index}:{machine_name}",
        title=title,
        mapping_platform=Platform.humble_key,
        ownership_platform=Platform.humble_key,
        owned_since=_parse_datetime(order.get("created")),
        owned_since_source="humble_order" if order.get("created") else None,
        feature_metadata_known=False,
    )


def _meta_entitlement_games(payload: Any) -> list[ImportedGame]:
    games: list[ImportedGame] = []
    seen: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            item = value.get("item")
            if isinstance(item, dict):
                game_id = str(item.get("id") or "").strip()
                title = str(item.get("display_name") or item.get("displayName") or "").strip()
                if game_id and title and game_id not in seen:
                    seen.add(game_id)
                    games.append(ImportedGame(platform_game_id=game_id, title=title, feature_metadata_known=False))
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(payload)
    return games


class MetaProvider:
    platform = Platform.meta
    authoritative_library = True

    def sync_account(self, account: Account) -> list[ImportedGame]:
        credentials = load_provider_auth_json(Platform.meta, account.id)
        access_token = str(credentials.get("access_token") or credentials.get("oc_ac_at") or "").strip()
        if not access_token:
            raise RuntimeError("Meta/Oculus-Zugriffstoken fehlt. Bitte den Account neu verbinden.")
        games: list[ImportedGame] = []
        seen: set[str] = set()
        with httpx.Client(timeout=40) as client:
            document_ids = [
                document_id.strip()
                for document_id in settings.meta_graphql_document_ids.split(",")
                if document_id.strip()
            ]
            for document_id in document_ids:
                response = client.post(
                    settings.meta_graphql_url,
                    data={"access_token": access_token, "doc_id": document_id},
                )
                response.raise_for_status()
                payload = response.json()
                if payload.get("errors"):
                    raise RuntimeError(f"Meta/Oculus-Anmeldung wurde abgelehnt: {payload['errors'][0].get('message', 'unbekannter Fehler')}")
                for game in _meta_entitlement_games(payload):
                    if game.platform_game_id not in seen:
                        seen.add(game.platform_game_id)
                        games.append(game)
        if not games:
            raise RuntimeError("Meta/Oculus hat keine Bibliothek zurückgegeben; vorhandene Daten bleiben erhalten.")
        return games

PROVIDERS: dict[Platform, ImportProvider] = {
    Platform.steam: SteamProvider(),
    Platform.epic: EpicProvider(),
    Platform.gog: GOGProvider(),
    Platform.xbox: XboxProvider(),
    Platform.ubisoft: UbisoftProvider(),
    Platform.ea: EAProvider(),
    Platform.amazon: AmazonProvider(),
    Platform.battle_net: BattleNetProvider(),
    Platform.humble: HumbleProvider(),
    Platform.meta: MetaProvider(),
}

























