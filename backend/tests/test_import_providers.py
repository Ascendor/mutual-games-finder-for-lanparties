import json
import time
from types import SimpleNamespace

import app.services.import_providers as import_providers
from app.models import Account, Platform
from app.services.import_providers import EAProvider, EpicProvider, GOG_CLIENT_ID, GOGProvider, SteamProvider, UbisoftProvider, XboxProvider


class FakeResponse:
    def __init__(self, payload, ok=True):
        self._payload = payload
        self.is_success = ok
        self.status_code = 200 if ok else 500

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class FakeClient:
    def __init__(self, headers=None, timeout=None):
        self.headers = headers or {}
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url):
        if url.endswith("/user/data/games"):
            return FakeResponse({"owned": [101]})
        if url.endswith("/products/101"):
            return FakeResponse(
                {
                    "title": "Stardew Valley",
                    "description": "Farming and friendship",
                    "genres": ["Simulation", "RPG"],
                    "playtime_seconds": 7200,
                }
            )
        if url.endswith("/account/gameDetails/101.json"):
            return FakeResponse({"owned_since": "2024-01-01T10:00:00Z", "singleplayer": True})
        return FakeResponse({}, ok=False)


def test_epic_provider_parses_legendary_json(monkeypatch):
    provider = EpicProvider()
    account = Account(id=42, participant_id=1, platform=Platform.epic, account_id="ignored")

    monkeypatch.setattr(
        import_providers.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout=json.dumps(
                [
                    {
                        "appName": "worldofgooo",
                        "app_title": "World of Goo",
                        "playtime_minutes": 90,
                        "genres": ["Puzzle"],
                    }
                ]
            ),
            stderr="",
            returncode=0,
        ),
    )

    games = provider.sync_account(account)

    assert len(games) == 1
    assert games[0].title == "World of Goo"
    assert games[0].platform_game_id == "worldofgooo"
    assert games[0].playtime_minutes == 90


def test_gog_provider_uses_auth_cache_and_direct_api(monkeypatch, tmp_path):
    monkeypatch.setattr(import_providers.settings, "provider_auth_root", str(tmp_path))
    cache = import_providers.gog_auth_config_path(7)
    cache.write_text(
        json.dumps(
            {
                GOG_CLIENT_ID: {
                    "access_token": "token",
                    "refresh_token": "refresh",
                    "expires_in": 3600,
                    "loginTime": time.time(),
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(import_providers.httpx, "Client", lambda **kwargs: FakeClient(**kwargs))

    provider = GOGProvider()
    account = Account(id=7, participant_id=1, platform=Platform.gog, account_id="ignored")

    games = provider.sync_account(account)

    assert len(games) == 1
    assert games[0].title == "Stardew Valley"
    assert games[0].playtime_minutes == 120
    assert games[0].singleplayer is True



def test_steam_provider_uses_playtime_forever(monkeypatch):
    provider = SteamProvider()
    account = Account(id=5, participant_id=1, platform=Platform.steam, account_id="7656119")

    class SteamClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, params=None, headers=None):
            return FakeResponse({"response": {"games": [{"appid": 620, "name": "Portal 2", "playtime_forever": 345}]}})

    monkeypatch.setattr(import_providers.settings, "steam_api_key", "key")
    monkeypatch.setattr(import_providers.settings, "steam_metadata_limit", 0)
    monkeypatch.setattr(import_providers.httpx, "Client", lambda **kwargs: SteamClient(**kwargs))

    games = provider.sync_account(account)

    assert games[0].playtime_minutes == 345


def test_xbox_provider_parses_title_history(monkeypatch, tmp_path):
    monkeypatch.setattr(import_providers.settings, "provider_auth_root", str(tmp_path))
    import_providers.save_provider_auth_json(
        Platform.xbox,
        9,
        {"xsts_token": "token", "user_hash": "hash", "xuid": "123"},
    )
    monkeypatch.setattr(
        import_providers.httpx,
        "get",
        lambda *args, **kwargs: FakeResponse({"titles": [{"titleId": "42", "name": "Halo Infinite"}]}),
    )

    games = XboxProvider().sync_account(Account(id=9, participant_id=1, platform=Platform.xbox, account_id="123"))

    assert len(games) == 1
    assert games[0].title == "Halo Infinite"
    assert games[0].platform_game_id == "42"


def test_ea_provider_parses_configured_library_endpoint(monkeypatch, tmp_path):
    monkeypatch.setattr(import_providers.settings, "provider_auth_root", str(tmp_path))
    import_providers.save_provider_auth_json(
        Platform.ea,
        10,
        {"access_token": "token", "library_url": "https://ea.example/library"},
    )
    class EAClient(FakeClient):
        def get(self, url):
            if url.endswith("/pids/me"):
                return FakeResponse({"pid": {"pidId": "123"}})
            if url == "https://ea.example/library":
                return FakeResponse({"games": [{"productId": "ea-1", "title": "Mass Effect"}]})
            return FakeResponse({}, ok=False)

    monkeypatch.setattr(import_providers.httpx, "Client", lambda **kwargs: EAClient(**kwargs))

    games = EAProvider().sync_account(Account(id=10, participant_id=1, platform=Platform.ea, account_id="ea"))

    assert len(games) == 1
    assert games[0].title == "Mass Effect"
    assert games[0].platform_game_id == "ea-1"



def test_provider_auth_status_accepts_string_platform(monkeypatch, tmp_path):
    from app.services import provider_auth

    monkeypatch.setattr(import_providers.settings, "provider_auth_root", str(tmp_path))
    account = Account(id=11, participant_id=1, platform="ubisoft", account_id="ubi")

    status = provider_auth.account_status(account)

    assert status["platform"] == Platform.ubisoft
    assert status["authenticated"] is False
    assert "ubisoft" in status["message"]


def test_ubisoft_complete_accepts_account_id_alias(monkeypatch, tmp_path):
    from app.services import provider_auth

    monkeypatch.setattr(import_providers.settings, "provider_auth_root", str(tmp_path))
    monkeypatch.setattr(
        provider_auth.httpx,
        "post",
        lambda *args, **kwargs: FakeResponse({"ticket": "ticket", "accountId": "profile-1", "sessionId": "session"}),
    )
    account = Account(id=12, participant_id=1, platform=Platform.ubisoft, account_id="local-ubi")

    result = provider_auth.complete(account, '{"email":"a@example.com","password":"secret"}')
    stored = import_providers.load_provider_auth_json(Platform.ubisoft, 12)

    assert result["authenticated"] is True
    assert stored["profileId"] == "profile-1"
    assert stored["ticket"] == "ticket"


def test_ubisoft_complete_stores_2fa_ticket(monkeypatch, tmp_path):
    from app.services import provider_auth

    monkeypatch.setattr(import_providers.settings, "provider_auth_root", str(tmp_path))
    monkeypatch.setattr(
        provider_auth.httpx,
        "post",
        lambda *args, **kwargs: FakeResponse({"twoFactorAuthenticationTicket": "2fa-ticket"}),
    )
    account = Account(id=13, participant_id=1, platform=Platform.ubisoft, account_id="local-ubi")

    result = provider_auth.complete(account, '{"email":"a@example.com","password":"secret"}')
    stored = import_providers.load_provider_auth_json(Platform.ubisoft, 13)
    status = provider_auth.account_status(account)

    assert result["authenticated"] is False
    assert result["needs_2fa"] is True
    assert stored["pending_2fa_ticket"] == "2fa-ticket"
    assert status["needs_2fa"] is True



def test_ubisoft_provider_parses_applications_library(monkeypatch, tmp_path):
    monkeypatch.setattr(import_providers.settings, "provider_auth_root", str(tmp_path))
    import_providers.save_provider_auth_json(
        Platform.ubisoft,
        14,
        {"ticket": "ticket", "profileId": "profile-1", "sessionId": "session"},
    )

    requested_urls = []

    class UbisoftClient:
        def __init__(self, headers=None, timeout=None):
            self.headers = headers or {}
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url):
            requested_urls.append(url)
            if "/applications/ubi-app-1" in url:
                return FakeResponse({"applicationId": "ubi-app-1", "name": "Beyond Good and Evil", "platform": "PC"})
            if "/applications/ubi-web-1" in url:
                return FakeResponse({"applicationId": "ubi-web-1", "name": "Ubisoft Forums", "platform": "WEB"})
            if "/applications" in url:
                return FakeResponse(
                    {
                        "applications": [
                            {
                                "applicationId": "ubi-app-1",
                                "firstSessionDate": "2024-02-03T10:00:00Z",
                                "sessionsCount": 4,
                            },
                            {"applicationId": "ubi-web-1"},
                        ]
                    }
                )
            return FakeResponse({}, ok=False)

    monkeypatch.setattr(import_providers.httpx, "Client", lambda **kwargs: UbisoftClient(**kwargs))

    games = UbisoftProvider().sync_account(Account(id=14, participant_id=1, platform=Platform.ubisoft, account_id="local-ubi"))

    assert len(games) == 1
    assert games[0].platform_game_id == "ubi-app-1"
    assert games[0].title == "Beyond Good and Evil"
    assert games[0].multiplayer is True
    assert any("limit=100" in url for url in requested_urls)


