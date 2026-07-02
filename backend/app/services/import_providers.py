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

import httpx
import yaml

from app.core.config import settings
from app.models import Account, Platform
from app.services.account_identity import apply_account_identity, is_placeholder_display_name
from app.services.normalization import normalize_title

GOG_CLIENT_ID = "46899977096215655"
GOG_CLIENT_SECRET = "9d85c43b1482497dbbce61f6e4aa173a433796eeae2ca8c5f6129f2dc4de46d9"
GOG_AUTH_URL = "https://auth.gog.com/token"
GOG_LOGIN_URL = "https://auth.gog.com/auth"
GOG_REDIRECT_URI = "https://embed.gog.com/on_login_success?origin=client"
GOG_EMBED_URL = "https://embed.gog.com"
GOG_API_URL = "https://api.gog.com"
GOG_DEFAULT_CACHE = Path.home() / ".config" / "heroic_gogdl" / "auth.json"
AMAZON_ENTITLEMENTS_URL = "https://gaming.amazon.com/api/distribution/entitlements"
AMAZON_TOKEN_URL = "https://api.amazon.com/auth/token"
LOGGER = logging.getLogger(__name__)

def platform_value(platform: Platform | str) -> str:
    return platform.value if isinstance(platform, Platform) else str(platform)


def coerce_platform(platform: Platform | str) -> Platform:
    return platform if isinstance(platform, Platform) else Platform(str(platform))


def provider_auth_dir(platform: Platform, account_id: int) -> Path:
    path = Path(settings.provider_auth_root) / platform_value(platform) / str(account_id)
    path.mkdir(parents=True, exist_ok=True)
    return path



def provider_auth_json_path(platform: Platform, account_id: int) -> Path:
    return provider_auth_dir(platform, account_id) / "auth.json"


def load_provider_auth_json(platform: Platform, account_id: int) -> dict[str, Any]:
    path = provider_auth_json_path(platform, account_id)
    if not path.exists():
        raise RuntimeError(f"{platform_value(platform)} is not connected. Open Provider-Logins and complete the account login first.")
    return json.loads(path.read_text(encoding="utf-8"))


def save_provider_auth_json(platform: Platform, account_id: int, payload: dict[str, Any]) -> None:
    path = provider_auth_json_path(platform, account_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _cookie_headers(credentials: dict[str, Any]) -> dict[str, str]:
    cookie = str(credentials.get("cookie") or credentials.get("cookies") or "").strip()
    if not cookie:
        raise RuntimeError("Die gespeicherte Browser-Sitzung fehlt. Bitte den Account neu verbinden.")
    # Firefox escapes Windows cmd metacharacters when copying a request as cURL.
    cookie = re.sub(r"\^(?=[&|<>()^$!])", "", cookie)
    return {
        "Cookie": cookie,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LANPartyGameFinder/1.0",
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
        owned_since=_parse_datetime(_first(app, "firstSessionDate", "firstDatePlayed", "createdAt")),
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


def _ea_pid_from_payload(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key in ("pidId", "pid_id", "pid", "userId", "user_id", "nucleusId", "nucleus_id"):
            value = payload.get(key)
            if value not in (None, ""):
                return str(value)
        for nested_key in ("pid", "user", "account", "persona"):
            nested = payload.get(nested_key)
            value = _ea_pid_from_payload(nested)
            if value:
                return value
        for value in payload.values():
            nested = _ea_pid_from_payload(value)
            if nested:
                return nested
    elif isinstance(payload, list):
        for item in payload:
            value = _ea_pid_from_payload(item)
            if value:
                return value
    return None


def _ea_game_from_entitlement(item: dict[str, Any], index: int) -> ImportedGame | None:
    data = _flatten_candidate(item)
    platform_game_id = str(
        _first(
            data,
            "offerId",
            "offer_id",
            "productId",
            "product_id",
            "entitlementId",
            "entitlement_id",
            "contentId",
            "content_id",
            "masterTitleId",
            "master_title_id",
            default=f"ea-{index}",
        )
    )
    title = _first(
        data,
        "displayName",
        "display_name",
        "title",
        "name",
        "productTitle",
        "product_title",
        "masterTitle",
        "master_title",
    )
    if not title:
        title = str(platform_game_id)
    return ImportedGame(
        platform_game_id=platform_game_id,
        title=str(title),
        owned_since=_parse_datetime(_first(data, "grantDate", "grant_date", "createdDate", "created_date", "date_purchased")),
        description=str(_first(data, "description", "longDescription", "shortDescription", default="") or ""),
        cover_url=_first(data, "packArtLarge", "packArtSmall", "image", "boxArt", "coverUrl", "cover_url"),
        release_date=_parse_date(_first(data, "releaseDate", "release_date")),
        genres=_as_list(_first(data, "genre", "genres")),
        multiplayer=True,
        min_players=1,
        max_players=1,
        feature_metadata_known=False,
    )


def _ea_games_from_payload(payload: Any) -> list[ImportedGame]:
    candidates = _collect_game_candidates(payload)
    if not candidates and isinstance(payload, dict):
        for key in ("entitlements", "baseGameEntitlements", "basegames", "games", "items", "offers"):
            value = payload.get(key)
            if isinstance(value, list):
                candidates = [item for item in value if isinstance(item, dict)]
                break
    games: list[ImportedGame] = []
    seen: set[str] = set()
    for index, item in enumerate(candidates):
        game = _ea_game_from_entitlement(item, index)
        if game and game.platform_game_id not in seen:
            seen.add(game.platform_game_id)
            games.append(game)
    return games


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

    def sync_account(self, account: Account) -> list[ImportedGame]:
        if not settings.steam_api_key:
            raise RuntimeError("STEAM_API_KEY is not configured")
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
                raise RuntimeError(
                    "Steam library is not accessible. In the Steam privacy settings, "
                    "set 'Game details' to 'Public' and try again."
                )
            games = steam_library.get("games") or []

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
                        headers={"User-Agent": "Mozilla/5.0 (LAN Party Game Finder)"},
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


STEAM_NON_GAME_TITLE = re.compile(
    r"\b(?:demo|dedicated\s+server|test\s+server|sdk)\b",
    re.IGNORECASE,
)


def _is_non_game_steam_entry(title: str, metadata: dict[str, Any]) -> bool:
    store_type = str(metadata.get("store_type") or "").casefold()
    if store_type and store_type != "game":
        return True
    return bool(STEAM_NON_GAME_TITLE.search(title))


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
        self.config_path.write_text(json.dumps(payload), encoding="utf-8")

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
            "User-Agent": "gogdl/0 (LAN Party Game Finder)",
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


UBISOFT_APP_ID = "f68a4bb5-608a-4ff2-8123-be8ef797e0a6"


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
            "User-Agent": "UbisoftConnect/1.0 LANPartyGameFinder",
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
        with httpx.Client(headers=headers, timeout=30) as client:
            for url in urls:
                response = client.get(url)
                if response.is_success:
                    payload = response.json()
                    games = _ubisoft_games_from_applications(payload, client) or _games_from_payload(payload, "ubisoft")
                    if games:
                        return games
                    errors.append(f"{url}: no games found")
                else:
                    errors.append(f"{url}: {response.status_code}")
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


class EAProvider:
    platform = Platform.ea

    def sync_account(self, account: Account) -> list[ImportedGame]:
        credentials = load_provider_auth_json(Platform.ea, account.id)
        token = credentials.get("access_token") or credentials.get("bearer") or credentials.get("token")
        cookie = credentials.get("cookie") or credentials.get("cookies")
        if not token and not cookie:
            raise RuntimeError("EA auth needs an access_token or browser cookie")
        headers: dict[str, str] = {
            "User-Agent": "EA app/13.0 LANPartyGameFinder",
            "Accept": "application/json",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if cookie:
            headers["Cookie"] = str(cookie)
        pid = credentials.get("pid") or credentials.get("pidId") or credentials.get("user_id") or credentials.get("userId") or credentials.get("nucleus_id") or credentials.get("nucleusId")
        errors: list[str] = []
        with httpx.Client(headers=headers, timeout=30) as client:
            if not pid:
                for url in (
                    "https://gateway.ea.com/proxy/identity/pids/me",
                    "https://gateway.ea.com/proxy/identity/personas/me",
                    "https://signin.ea.com/p/web2/pid/me",
                ):
                    response = client.get(url)
                    if response.is_success:
                        pid = _ea_pid_from_payload(response.json())
                        if pid:
                            break
                        errors.append(f"{url}: no pid found")
                    else:
                        errors.append(f"{url}: {response.status_code}")
            if not pid:
                raise RuntimeError("EA sync needs a pid/user_id or a token that can read pids/me: " + "; ".join(errors[-3:]))
            machine_hash = str(credentials.get("machine_hash") or credentials.get("machineHash") or "1")
            urls = [
                f"https://api1.origin.com/ecommerce2/basegames/{pid}/entitlements?machine_hash={machine_hash}",
                f"https://api1.origin.com/ecommerce2/basegames/{pid}/entitlements",
                f"https://gateway.ea.com/proxy/ecommerce2/basegames/{pid}/entitlements?machine_hash={machine_hash}",
                f"https://gateway.ea.com/proxy/ecommerce2/basegames/{pid}/entitlements",
            ]
            custom_url = credentials.get("entitlements_url") or credentials.get("library_url")
            if custom_url:
                urls.insert(0, str(custom_url))
            for url in urls:
                response = client.get(url)
                if response.is_success:
                    payload = response.json()
                    games = _ea_games_from_payload(payload) or _games_from_payload(payload, "ea")
                    if games:
                        return games
                    errors.append(f"{url}: no games found")
                else:
                    errors.append(f"{url}: {response.status_code}")
        raise RuntimeError("EA sync did not return a library: " + "; ".join(errors[-4:]))


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
            for document_id in ("9431935310238631", "29383114651302983", "29143116735333849"):
                response = client.post(
                    "https://graph.oculus.com/graphql?locale=en_US",
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

































