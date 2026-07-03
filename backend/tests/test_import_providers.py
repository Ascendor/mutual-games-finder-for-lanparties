import json
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

import app.services.import_providers as import_providers
from app.models import Account, Platform
from app.services.account_identity import apply_account_identity, is_placeholder_display_name
from app.services.import_providers import (
    AmazonProvider,
    BattleNetProvider,
    EAProvider,
    EpicProvider,
    GOG_CLIENT_ID,
    GOGProvider,
    HumbleProvider,
    ImportBatch,
    MetaProvider,
    SteamProvider,
    UbisoftProvider,
    XboxProvider,
    _resolved_gog_title,
)


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
        if url.endswith("/userData.json"):
            return FakeResponse({"userId": "gog-user-7", "username": "PlayerOneOnGOG"})
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
                    },
                    {
                        "appName": "digitalextras",
                        "app_title": "Soundtrack and Artbook",
                        "metadata": {"categories": [{"path": "games"}, {"path": "digitalextras"}]},
                    },
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
    account = Account(
        id=7,
        participant_id=1,
        platform=Platform.gog,
        account_id="ignored",
        display_name="GOG",
    )

    batch = provider.sync_account(account)
    assert isinstance(batch, ImportBatch)
    games = batch.games

    assert len(games) == 1
    assert games[0].title == "Stardew Valley"
    assert games[0].playtime_minutes == 120
    assert games[0].singleplayer is True
    assert batch.warnings == []
    assert batch.authoritative_snapshot is True
    assert provider.authoritative_library is True
    assert account.display_name == "PlayerOneOnGOG"


def test_epic_provider_repairs_placeholder_display_name_from_legendary_status(monkeypatch):
    account = Account(
        id=42,
        participant_id=1,
        platform=Platform.epic,
        account_id="local-epic-1-1",
        display_name="Epic Games",
    )

    def fake_run(command, *args, **kwargs):
        if "status" in command:
            return SimpleNamespace(
                stdout=json.dumps({"account": "EpicPlayerOne"}),
                stderr="",
                returncode=0,
            )
        return SimpleNamespace(stdout="[]", stderr="", returncode=0)

    monkeypatch.setattr(import_providers.subprocess, "run", fake_run)

    EpicProvider().sync_account(account)

    assert account.display_name == "EpicPlayerOne"


def test_account_identity_uses_participant_only_as_placeholder_fallback():
    from app.models import Participant

    participant = Participant(nickname="PlayerOne")
    account = Account(
        participant=participant,
        platform=Platform.humble,
        account_id="local-humble-1-1",
        display_name="Humble",
    )

    assert is_placeholder_display_name(account) is True
    assert apply_account_identity(account, participant_fallback=True) is True
    assert account.display_name == "PlayerOne (Teilnehmer)"


def test_gog_provider_skips_one_unresolved_product_without_claiming_complete_snapshot(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(import_providers.settings, "provider_auth_root", str(tmp_path))
    cache = import_providers.gog_auth_config_path(8)
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

    class PartialGOGClient(FakeClient):
        def get(self, url):
            if url.endswith("/user/data/games"):
                return FakeResponse({"owned": [101, 1173343803]})
            if url.endswith("/products/101"):
                return FakeResponse({"title": "Stardew Valley"})
            if url.endswith("/account/gameDetails/101.json"):
                return FakeResponse({})
            if url.endswith("/products/1173343803"):
                return FakeResponse({"title": "product_title_1173343803"})
            if url.endswith("/account/gameDetails/1173343803.json"):
                return FakeResponse({})
            return FakeResponse({}, ok=False)

    monkeypatch.setattr(
        import_providers.httpx,
        "Client",
        lambda **kwargs: PartialGOGClient(**kwargs),
    )

    batch = GOGProvider().sync_account(
        Account(id=8, participant_id=1, platform=Platform.gog, account_id="ignored")
    )

    assert isinstance(batch, ImportBatch)
    assert [game.title for game in batch.games] == ["Stardew Valley"]
    assert batch.authoritative_snapshot is False
    assert len(batch.warnings) == 1
    assert "1173343803" in batch.warnings[0]


def test_gog_provider_fails_when_no_owned_product_can_be_resolved(monkeypatch, tmp_path):
    monkeypatch.setattr(import_providers.settings, "provider_auth_root", str(tmp_path))
    cache = import_providers.gog_auth_config_path(9)
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

    class BrokenGOGClient(FakeClient):
        def get(self, url):
            if url.endswith("/user/data/games"):
                return FakeResponse({"owned": [1173343803]})
            if url.endswith("/products/1173343803"):
                return FakeResponse({"title": "product_title_1173343803"})
            return FakeResponse({})

    monkeypatch.setattr(
        import_providers.httpx,
        "Client",
        lambda **kwargs: BrokenGOGClient(**kwargs),
    )

    with pytest.raises(RuntimeError, match="Keines der 1 GOG-Produkte"):
        GOGProvider().sync_account(
            Account(id=9, participant_id=1, platform=Platform.gog, account_id="ignored")
        )


def test_gog_title_resolution_rejects_localization_tokens():
    assert _resolved_gog_title(
        {"title": "product_title_2034259767"},
        {"title": "STAR WARS Jedi Knight: Dark Forces II"},
    ) == "STAR WARS Jedi Knight: Dark Forces II"
    assert _resolved_gog_title(
        {"title": "product_title_2034259767"},
        {},
    ) is None



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
            return FakeResponse(
                {
                    "response": {
                        "game_count": 1,
                        "games": [
                            {
                                "appid": 620,
                                "name": "Portal 2",
                                "playtime_forever": 345,
                            }
                        ],
                    }
                }
            )

    monkeypatch.setattr(import_providers.settings, "steam_api_key", "key")
    monkeypatch.setattr(import_providers.settings, "steam_metadata_limit", 0)
    monkeypatch.setattr(import_providers.httpx, "Client", lambda **kwargs: SteamClient(**kwargs))

    games = provider.sync_account(account)

    assert games[0].playtime_minutes == 345


def test_steam_provider_rejects_inaccessible_library(monkeypatch):
    account = Account(id=5, participant_id=1, platform=Platform.steam, account_id="7656119")

    class PrivateSteamClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, params=None, headers=None):
            return FakeResponse({"response": {}})

    monkeypatch.setattr(import_providers.settings, "steam_api_key", "key")
    monkeypatch.setattr(
        import_providers.httpx,
        "Client",
        lambda **kwargs: PrivateSteamClient(**kwargs),
    )

    with pytest.raises(RuntimeError, match="Game details"):
        SteamProvider().sync_account(account)


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
        lambda *args, **kwargs: FakeResponse(
            {
                "titles": [
                    {
                        "titleId": "42",
                        "pfn": "Microsoft.HaloInfinite",
                        "name": "Halo Infinite",
                        "type": "Game",
                        "devices": ["PC", "XboxSeries"],
                        "minutesPlayed": "120",
                    },
                    {
                        "titleId": "99",
                        "name": "Console only",
                        "type": "Game",
                        "devices": ["XboxSeries"],
                    },
                ]
            }
        ),
    )

    games = XboxProvider().sync_account(Account(id=9, participant_id=1, platform=Platform.xbox, account_id="123"))

    assert len(games) == 1
    assert games[0].title == "Halo Infinite"
    assert games[0].platform_game_id == "Microsoft.HaloInfinite"
    assert games[0].playtime_minutes == 120


def test_ea_provider_reads_graphql_library_and_playtime(monkeypatch, tmp_path):
    monkeypatch.setattr(import_providers.settings, "provider_auth_root", str(tmp_path))
    import_providers.save_provider_auth_json(
        Platform.ea,
        10,
        {"access_token": "token"},
    )

    class EAClient(FakeClient):
        def get(self, url):
            query = parse_qs(urlparse(url).query)
            if query.get("operationName") == ["getPreloadedOwnedGames"]:
                return FakeResponse(
                    {
                        "data": {
                            "me": {
                                "ownedGameProducts": {
                                    "next": None,
                                    "totalCount": 1,
                                    "items": [
                                        {
                                            "originOfferId": "ea-1",
                                            "product": {
                                                "name": "Mass Effect",
                                                "gameSlug": "mass-effect",
                                                "gameProductUser": {
                                                    "initialEntitlementDate": "2024-01-02T12:00:00Z",
                                                },
                                            },
                                        }
                                    ]
                                }
                            }
                        }
                    }
                )
            if query.get("operationName") == ["GetGamePlayTimes"]:
                return FakeResponse(
                    {
                        "data": {
                            "me": {
                                "recentGames": {
                                    "items": [
                                        {
                                            "gameSlug": "mass-effect",
                                            "totalPlayTimeSeconds": 7200,
                                            "lastSessionEndDate": "2026-01-01T12:00:00Z",
                                        }
                                    ]
                                }
                            }
                        }
                    }
                )
            return FakeResponse({}, ok=False)

    monkeypatch.setattr(import_providers.httpx, "Client", lambda **kwargs: EAClient(**kwargs))

    result = EAProvider().sync_account(Account(id=10, participant_id=1, platform=Platform.ea, account_id="ea"))

    assert isinstance(result, ImportBatch)
    assert len(result.games) == 1
    assert result.games[0].title == "Mass Effect"
    assert result.games[0].platform_game_id == "ea-1"
    assert result.games[0].playtime_minutes == 120


def test_ea_provider_accepts_filtered_count_without_next_cursor(monkeypatch, tmp_path):
    monkeypatch.setattr(import_providers.settings, "provider_auth_root", str(tmp_path))
    import_providers.save_provider_auth_json(Platform.ea, 10, {"access_token": "token"})

    class PartialEAClient(FakeClient):
        def get(self, url):
            return FakeResponse(
                {
                    "data": {
                        "me": {
                            "ownedGameProducts": {
                                "items": [
                                    {
                                        "originOfferId": "ea-1",
                                        "product": {"name": "Mass Effect", "gameSlug": "mass-effect"},
                                    }
                                ],
                                "next": None,
                                "totalCount": 2,
                            }
                        }
                    }
                }
            )

    monkeypatch.setattr(import_providers.httpx, "Client", lambda **kwargs: PartialEAClient(**kwargs))

    result = EAProvider().sync_account(
        Account(id=10, participant_id=1, platform=Platform.ea, account_id="ea")
    )

    assert len(result.games) == 1
    assert result.authoritative_snapshot is False
    assert any("meldete 2 Einträge" in warning for warning in result.warnings)


def test_ea_provider_keeps_valid_games_when_later_page_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(import_providers.settings, "provider_auth_root", str(tmp_path))
    import_providers.save_provider_auth_json(Platform.ea, 10, {"access_token": "token"})

    class FailingSecondPageEAClient(FakeClient):
        def get(self, url):
            query = parse_qs(urlparse(url).query)
            if query.get("operationName") == ["GetGamePlayTimes"]:
                return FakeResponse({"data": {"me": {"recentGames": {"items": []}}}})
            variables = json.loads(query["variables"][0])
            if variables["next"] == "0":
                return FakeResponse(
                    {
                        "data": {
                            "me": {
                                "ownedGameProducts": {
                                    "items": [
                                        {
                                            "originOfferId": "ea-1",
                                            "product": {"name": "Mass Effect", "gameSlug": "mass-effect"},
                                        }
                                    ],
                                    "next": "page-2",
                                    "totalCount": 2,
                                }
                            }
                        }
                    }
                )
            return FakeResponse({}, ok=False)

    monkeypatch.setattr(
        import_providers.httpx,
        "Client",
        lambda **kwargs: FailingSecondPageEAClient(**kwargs),
    )

    result = EAProvider().sync_account(
        Account(id=10, participant_id=1, platform=Platform.ea, account_id="ea")
    )

    assert [game.title for game in result.games] == ["Mass Effect"]
    assert result.authoritative_snapshot is False
    assert any("Bibliotheksseite" in warning for warning in result.warnings)



def test_provider_auth_status_accepts_string_platform(monkeypatch, tmp_path):
    from app.services import provider_auth

    monkeypatch.setattr(import_providers.settings, "provider_auth_root", str(tmp_path))
    account = Account(id=11, participant_id=1, platform="ubisoft", account_id="ubi")

    status = provider_auth.account_status(account)

    assert status["platform"] == Platform.ubisoft
    assert status["authenticated"] is False
    assert "ubisoft" in status["message"]


def test_provider_auth_cleans_common_epic_paste_variants():
    from app.services.provider_auth import _clean_epic_code, _epic_identity_from_output

    assert _clean_epic_code('"abc-123"') == "abc-123"
    assert _clean_epic_code("'abc-123'") == "abc-123"
    assert _clean_epic_code('{"authorizationCode": "abc-123"}') == "abc-123"
    assert _clean_epic_code('```json\n{"AuthorizationCode": "abc-123"}\n```') == "abc-123"
    assert _clean_epic_code('authorizationCode: "abc-123"') == "abc-123"
    assert _clean_epic_code("https://example.test/callback?authorizationCode=abc-123") == "abc-123"
    assert _epic_identity_from_output('Successfully logged in as "EpicPlayerOne"') == {
        "provider_display_name": "EpicPlayerOne"
    }


def test_provider_auth_cleans_common_gog_paste_variants():
    from app.services.provider_auth import _clean_gog_code

    assert _clean_gog_code('"gog-code"') == "gog-code"
    assert _clean_gog_code('{"code": "gog-code"}') == "gog-code"
    assert _clean_gog_code("code='gog-code'") == "gog-code"
    assert _clean_gog_code("https://embed.gog.com/on_login_success?code=gog-code") == "gog-code"


def test_gog_login_returns_provider_identity(monkeypatch, tmp_path):
    from app.services import provider_auth

    monkeypatch.setattr(import_providers.settings, "provider_auth_root", str(tmp_path))

    def fake_get(url, **kwargs):
        if url == import_providers.GOG_AUTH_URL:
            return FakeResponse(
                {
                    "access_token": "gog-access",
                    "refresh_token": "gog-refresh",
                    "expires_in": 3600,
                    "user_id": "gog-user-7",
                }
            )
        return FakeResponse({"userId": "gog-user-7", "username": "PlayerOneOnGOG"})

    monkeypatch.setattr(provider_auth.httpx, "get", fake_get)
    account = Account(
        id=37,
        participant_id=1,
        platform=Platform.gog,
        account_id="local-gog-1-1",
        display_name="GOG",
    )

    result = provider_auth.complete_gog(account, "gog-code")

    assert result["provider_account_id"] == "gog-user-7"
    assert result["provider_display_name"] == "PlayerOneOnGOG"


def test_provider_login_persists_resolved_identity(monkeypatch, db):
    from app.api import provider_auth as provider_auth_api
    from app.models import Participant

    participant = Participant(nickname="PlayerOne")
    db.add(participant)
    db.flush()
    account = Account(
        participant_id=participant.id,
        platform=Platform.gog,
        account_id="local-gog-1-1",
        display_name="GOG",
    )
    db.add(account)
    db.commit()
    monkeypatch.setattr(
        provider_auth_api.provider_auth,
        "complete",
        lambda *args, **kwargs: {
            "authenticated": True,
            "provider_account_id": "gog-user-7",
            "provider_display_name": "PlayerOneOnGOG",
        },
    )

    provider_auth_api.complete_login(
        account.id,
        provider_auth_api.ProviderCodePayload(code="accepted"),
        db,
    )

    db.refresh(account)
    assert account.account_id == "gog-user-7"
    assert account.display_name == "PlayerOneOnGOG"


def test_provider_auth_extracts_firefox_curl_and_cookie_json():
    from app.services.provider_auth import _extract_browser_cookie

    curl = """curl 'https://account.battle.net/api/games-and-subs' -H 'Accept: application/json' -H 'Cookie: sid=abc; region=eu'"""
    windows_curl = """curl "https://www.humblebundle.com/api/v1/user/order" -H "Cookie: _simpleauth_sess=left^|middle^|right; OPTY^$name=value" """
    cookie_json = '[{"name":"oc_ac_at","value":"meta-token"},{"name":"locale","value":"de_DE"}]'

    assert _extract_browser_cookie(curl) == "sid=abc; region=eu"
    assert _extract_browser_cookie(windows_curl) == "_simpleauth_sess=left|middle|right; OPTY$name=value"
    assert _extract_browser_cookie(cookie_json) == "oc_ac_at=meta-token; locale=de_DE"


def test_provider_auth_stores_meta_access_token(monkeypatch, tmp_path):
    from app.services import provider_auth

    monkeypatch.setattr(import_providers.settings, "provider_auth_root", str(tmp_path))
    account = Account(id=31, participant_id=1, platform=Platform.meta, account_id="local-meta-1-1")

    result = provider_auth.complete(
        account,
        """curl 'https://secure.oculus.com/my/profile/' -H 'Cookie: locale=de_DE; oc_ac_at=meta-token; session=abc'""",
    )
    stored = import_providers.load_provider_auth_json(Platform.meta, 31)

    assert result["authenticated"] is True
    assert stored == {"access_token": "meta-token"}
    assert provider_auth.account_status(account)["authenticated"] is True


def test_amazon_login_exchanges_callback_for_refreshable_tokens(monkeypatch, tmp_path):
    from app.services import provider_auth

    monkeypatch.setattr(import_providers.settings, "provider_auth_root", str(tmp_path))
    account = Account(id=32, participant_id=1, platform=Platform.amazon, account_id="local-amazon-1-1")
    start = provider_auth.start(account)
    monkeypatch.setattr(
        provider_auth.httpx,
        "post",
        lambda *args, **kwargs: FakeResponse(
            {
                "response": {
                    "success": {
                        "tokens": {
                            "bearer": {
                                "access_token": "amazon-access",
                                "refresh_token": "amazon-refresh",
                                "expires_in": 3600,
                            }
                        }
                    }
                }
            }
        ),
    )

    result = provider_auth.complete(
        account,
        "https://www.amazon.com/?openid.oa2.authorization_code=amazon-code",
    )
    stored = import_providers.load_provider_auth_json(Platform.amazon, 32)
    login_query = parse_qs(urlparse(start["login_url"]).query)
    client_id = login_query["openid.oa2.client_id"][0].removeprefix("device:")

    assert "openid.oa2.code_challenge=" in start["login_url"]
    assert bytes.fromhex(client_id).decode("ascii").endswith("#A2UMVHOX7UP4V7")
    assert result["authenticated"] is True
    assert stored["refresh_token"] == "amazon-refresh"


def test_amazon_provider_reads_entitlements(monkeypatch, tmp_path):
    monkeypatch.setattr(import_providers.settings, "provider_auth_root", str(tmp_path))
    import_providers.save_provider_auth_json(
        Platform.amazon,
        33,
        {
            "access_token": "amazon-access",
            "refresh_token": "amazon-refresh",
            "expires_at": time.time() + 3600,
            "device_serial": "0123456789abcdef0123456789abcdef",
        },
    )

    class AmazonClient:
        def __init__(self, **kwargs):
            self.headers = kwargs.get("headers", {})

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json=None):
            assert json["Operation"] == "GetEntitlements"
            assert json["clientId"] == "Sonic"
            assert len(json["hardwareHash"]) == 64
            return FakeResponse(
                {
                    "entitlements": [
                        {
                            "product": {
                                "id": "amazon-game-1",
                                "title": "The Forgotten City",
                                "productLine": "Amazon:Game",
                                "productDetail": {"iconUrl": "https://example.test/icon.jpg"},
                            }
                        }
                    ]
                }
            )

    monkeypatch.setattr(import_providers.httpx, "Client", lambda **kwargs: AmazonClient(**kwargs))
    games = AmazonProvider().sync_account(
        Account(id=33, participant_id=1, platform=Platform.amazon, account_id="local-amazon-1-1")
    )

    assert len(games) == 1
    assert games[0].platform_game_id == "amazon-game-1"


def test_provider_auth_accepts_ea_curl_and_stores_only_token(monkeypatch, tmp_path):
    from app.services import provider_auth

    monkeypatch.setattr(import_providers.settings, "provider_auth_root", str(tmp_path))
    monkeypatch.setattr(
        provider_auth,
        "validate_ea_access_token",
        lambda token: {"me": {"id": "ea-user-1", "displayName": "Commander Shepard"}},
    )
    account = Account(id=99, participant_id=1, platform=Platform.ea, account_id="local-ea")
    curl = """curl 'https://service-aggregation-layer.juno.ea.com/graphql?operationName=getPreloadedOwnedGames' \
      -H 'accept: application/json' \
      -H 'authorization: Bearer ea-token.with.dots-1234567890' \
      -H 'cookie: session=must-not-be-stored'"""

    result = provider_auth.complete(account, curl)
    stored = import_providers.load_provider_auth_json(Platform.ea, 99)

    assert result["authenticated"] is True
    assert stored["access_token"] == "ea-token.with.dots-1234567890"
    assert "cookie" not in stored
    assert "curl" not in stored
    assert provider_auth._extract_ea_bearer(
        'curl.exe ^"https://service-aggregation-layer.juno.ea.com/graphql^" '
        '^-H ^"Authorization: Bearer edge-token.with.dots-1234567890^"'
    ) == "edge-token.with.dots-1234567890"


def test_provider_auth_rejects_wrong_ea_curl():
    from app.services import provider_auth

    account = Account(id=99, participant_id=1, platform=Platform.ea, account_id="local-ea")

    with pytest.raises(ValueError, match="juno.ea.com/graphql"):
        provider_auth.complete(
            account,
            "curl 'https://www.ea.com/' -H 'Authorization: Bearer ea-token.with.dots-1234567890'",
        )


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


def test_battlenet_provider_reads_web_session_library(monkeypatch, tmp_path):
    monkeypatch.setattr(import_providers.settings, "provider_auth_root", str(tmp_path))
    import_providers.save_provider_auth_json(Platform.battle_net, 41, {"cookie": "sid=abc"})

    class BattleNetClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url):
            if url.endswith("/api/"):
                return FakeResponse({"authenticated": True})
            if url.endswith("games-and-subs"):
                return FakeResponse({"gameAccounts": [{"titleId": 123, "localizedGameName": "Diablo IV"}]})
            return FakeResponse({"classicGames": [{"localizedGameName": "Diablo II", "regionalGameFranchiseIconFilename": "diablo-ii"}]})

    monkeypatch.setattr(import_providers.httpx, "Client", lambda **kwargs: BattleNetClient(**kwargs))
    games = BattleNetProvider().sync_account(
        Account(id=41, participant_id=1, platform=Platform.battle_net, account_id="local-battle_net-1-1")
    )

    assert [game.title for game in games] == ["Diablo IV", "Diablo II"]


def test_humble_provider_reads_windows_games(monkeypatch, tmp_path):
    monkeypatch.setattr(import_providers.settings, "provider_auth_root", str(tmp_path))
    import_providers.save_provider_auth_json(Platform.humble, 42, {"cookie": "_simpleauth_sess=left^|right"})

    class HumbleResponse(FakeResponse):
        def __init__(self, payload=None, text=""):
            super().__init__(payload or {})
            self.text = text
            self.headers = {"content-type": "application/json; charset=utf-8"}

    class HumbleClient:
        def __init__(self, **kwargs):
            assert kwargs["headers"]["Cookie"] == "_simpleauth_sess=left|right"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, params=None):
            if url.endswith("/api/v1/user/order"):
                return HumbleResponse([{"gamekey": "key-1"}])
            return HumbleResponse(
                {
                    "key-1": {
                        "gamekey": "key-1",
                        "subproducts": [
                            {
                                "machine_name": "ftl",
                                "human_name": "FTL: Faster Than Light",
                                "downloads": [{"platform": "windows"}],
                            }
                        ],
                        "tpkd_dict": {
                            "all_tpks": [
                                {
                                    "human_name": "The Walking Dead",
                                    "machine_name": "walking-dead",
                                    "key_type": "steam",
                                    "key_type_human_name": "Steam",
                                    "keyindex": 1,
                                    "visible": True,
                                    "is_expired": False,
                                    "sold_out": False,
                                },
                                {
                                    "human_name": "Already revealed",
                                    "key_type": "steam",
                                    "keyindex": 2,
                                    "visible": True,
                                    "is_expired": False,
                                    "redeemed_key_val": "never-store-this",
                                },
                                {
                                    "human_name": "Expired Game",
                                    "key_type": "gog",
                                    "keyindex": 3,
                                    "visible": True,
                                    "is_expired": True,
                                },
                                {
                                    "human_name": "Python Course",
                                    "key_type": "external_key",
                                    "key_type_human_name": "MetaSnake",
                                    "keyindex": 4,
                                    "visible": True,
                                    "is_expired": False,
                                },
                            ]
                        },
                    }
                }
            )

    monkeypatch.setattr(import_providers.httpx, "Client", lambda **kwargs: HumbleClient(**kwargs))
    games = HumbleProvider().sync_account(
        Account(id=42, participant_id=1, platform=Platform.humble, account_id="local-humble-1-1")
    )

    assert len(games) == 2
    assert games[0].platform_game_id == "ftl"
    assert games[1].title == "The Walking Dead"
    assert games[1].mapping_platform == Platform.humble_key
    assert games[1].ownership_platform == Platform.humble_key


def test_meta_provider_combines_pc_and_quest_entitlements(monkeypatch, tmp_path):
    monkeypatch.setattr(import_providers.settings, "provider_auth_root", str(tmp_path))
    import_providers.save_provider_auth_json(Platform.meta, 43, {"access_token": "token"})

    class MetaClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, data=None):
            document_id = data["doc_id"]
            item = {"id": document_id, "display_name": f"Game {document_id}"}
            return FakeResponse({"data": {"viewer": {"user": {"entitlements": {"edges": [{"node": {"item": item}}]}}}}})

    monkeypatch.setattr(import_providers.httpx, "Client", lambda **kwargs: MetaClient(**kwargs))
    games = MetaProvider().sync_account(
        Account(id=43, participant_id=1, platform=Platform.meta, account_id="local-meta-1-1")
    )

    assert len(games) == 3


