import json
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api import provider_auth as provider_auth_api
from app.core.config import settings
from app.models import Account, Participant, Platform
from app.services import provider_auth as provider_auth_service
from app.services import steam_auth, steam_client_auth, steam_openid
from app.services.steam_auth import SteamProfile


class FakeResponse:
    def __init__(self, payload=None, text: str = ""):
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


def test_resolve_steam_profile_accepts_quoted_vanity_url(monkeypatch):
    monkeypatch.setattr(settings, "steam_api_key", "test-key")
    calls: list[str] = []

    def fake_get(url, **kwargs):
        calls.append(url)
        if "ResolveVanityURL" in url:
            assert kwargs["params"]["vanityurl"] == "Ada_Player"
            return FakeResponse({"response": {"success": 1, "steamid": "76561198000000001"}})
        if "GetPlayerSummaries" in url:
            return FakeResponse(
                {
                    "response": {
                        "players": [
                            {
                                "personaname": "Ada",
                                "profileurl": "https://steamcommunity.com/id/Ada_Player/",
                                "avatarfull": "https://cdn.example/avatar.jpg",
                            }
                        ]
                    }
                }
            )
        return FakeResponse({"response": {"game_count": 123}})

    monkeypatch.setattr(steam_auth.httpx, "get", fake_get)
    profile = steam_auth.resolve_steam_profile(
        '"https://steamcommunity.com/id/Ada_Player/?utm_source=test"'
    )

    assert profile.steam_id == "76561198000000001"
    assert profile.display_name == "Ada"
    assert profile.game_count == 123
    assert profile.library_accessible is True
    assert len(calls) == 3


def test_resolve_steam_profile_reports_private_library(monkeypatch):
    monkeypatch.setattr(settings, "steam_api_key", "test-key")

    def fake_get(url, **kwargs):
        if "GetPlayerSummaries" in url:
            return FakeResponse(
                {"response": {"players": [{"personaname": "Private", "profileurl": "https://example"}]}}
            )
        return FakeResponse({"response": {}})

    monkeypatch.setattr(steam_auth.httpx, "get", fake_get)
    profile = steam_auth.resolve_steam_profile("76561198000000002")

    assert profile.library_accessible is False
    assert profile.game_count is None


def test_upsert_steam_account_reconnects_existing_participant(db):
    participant = Participant(nickname="Ada", present=True)
    db.add(participant)
    db.flush()
    existing = Account(
        participant_id=participant.id,
        platform=Platform.steam,
        account_id="76561198000000004",
        display_name="Old",
    )
    db.add(existing)
    db.commit()

    profile = SteamProfile(
        steam_id="76561198000000005",
        display_name="New",
        profile_url="https://steamcommunity.com/profiles/76561198000000005/",
        avatar_url=None,
        library_accessible=True,
        game_count=42,
    )
    account = steam_auth.upsert_steam_account(db, participant.id, profile)

    assert account.id == existing.id
    assert account.account_id == profile.steam_id
    assert account.display_name == "New"


def test_connect_does_not_replace_existing_account_with_private_library(monkeypatch, db):
    participant = Participant(nickname="Ada", present=True)
    db.add(participant)
    db.flush()
    existing = Account(
        participant_id=participant.id,
        platform=Platform.steam,
        account_id="76561198000000004",
        display_name="Old",
    )
    db.add(existing)
    db.commit()
    private_profile = SteamProfile(
        steam_id="76561198000000005",
        display_name="Private",
        profile_url="https://steamcommunity.com/profiles/76561198000000005/",
        avatar_url=None,
        library_accessible=False,
        game_count=None,
    )
    monkeypatch.setattr(provider_auth_api, "resolve_steam_profile", lambda reference: private_profile)

    with pytest.raises(HTTPException) as error:
        provider_auth_api.connect_steam(
            provider_auth_api.SteamConnectPayload(
                participant_id=participant.id,
                profile=private_profile.steam_id,
            ),
            db,
        )

    assert error.value.status_code == 400
    db.refresh(existing)
    assert existing.account_id == "76561198000000004"


def test_community_id_connection_removes_stored_refresh_token(monkeypatch, db, tmp_path):
    participant = Participant(nickname="Ada", present=True)
    db.add(participant)
    db.flush()
    existing = Account(
        participant_id=participant.id,
        platform=Platform.steam,
        account_id="76561198000000004",
        display_name="Old",
    )
    db.add(existing)
    db.commit()
    profile = SteamProfile(
        steam_id="76561198000000005",
        display_name="Public",
        profile_url="https://steamcommunity.com/profiles/76561198000000005/",
        avatar_url=None,
        library_accessible=True,
        game_count=42,
    )
    monkeypatch.setattr(provider_auth_api, "resolve_steam_profile", lambda reference: profile)
    monkeypatch.setattr(settings, "provider_auth_root", str(tmp_path))
    credentials = tmp_path / "steam" / str(existing.id) / "auth.json"
    credentials.parent.mkdir(parents=True)
    credentials.write_text('{"refresh_token":"remove-me"}', encoding="utf-8")

    connection = provider_auth_api.connect_steam(
        provider_auth_api.SteamConnectPayload(
            participant_id=participant.id,
            profile=profile.steam_id,
        ),
        db,
    )

    account = connection["account"]
    assert account.id == existing.id
    assert not credentials.exists()
    assert provider_auth_service.account_status(account)["connection_mode"] == "community"


def test_imported_steam_account_has_no_direct_connection_mode(db, tmp_path, monkeypatch):
    participant = Participant(nickname="Ada", present=True)
    db.add(participant)
    db.flush()
    account = Account(
        participant_id=participant.id,
        platform=Platform.steam,
        account_id="playnite:steam:ada",
        display_name="Playnite",
    )
    db.add(account)
    db.commit()
    monkeypatch.setattr(settings, "provider_auth_root", str(tmp_path))

    status = provider_auth_service.account_status(account)

    assert status["connection_mode"] is None


def test_steam_qr_login_creates_account_and_imports_license_dates(monkeypatch, client, db, tmp_path):
    participant = Participant(nickname="Ada", present=True)
    db.add(participant)
    db.commit()

    profile = SteamProfile(
        steam_id="76561198000000006",
        display_name="AdaSteam",
        profile_url="https://steamcommunity.com/profiles/76561198000000006/",
        avatar_url=None,
        library_accessible=True,
        game_count=99,
    )
    monkeypatch.setattr(
        provider_auth_api,
        "start_steam_qr_login",
        lambda: {"state": "qr-state", "qr_data_url": "data:image/png;base64,test", "expires_in": 180},
    )
    monkeypatch.setattr(
        provider_auth_api,
        "poll_steam_qr_login",
        lambda state: {
            "status": "complete",
            "steam_id": profile.steam_id,
            "account_name": "AdaSteam",
            "refresh_token": "remember-me",
            "games": [
                {
                    "appid": "620",
                    "title": "Portal 2",
                    "owned_since": "2024-01-02T03:04:05.000Z",
                }
            ],
        },
    )
    monkeypatch.setattr(steam_client_auth, "resolve_steam_profile", lambda reference: profile)
    monkeypatch.setattr(settings, "provider_auth_root", str(tmp_path))
    provider_auth_api._pending_steam_logins.clear()

    try:
        start = client.post(
            "/api/provider-auth/steam/start",
            json={"participant_id": participant.id},
        )
        assert start.status_code == 200
        payload = start.json()
        assert payload["qr_data_url"].startswith("data:image/png")

        completed = client.get(f"/api/provider-auth/steam/poll/{payload['state']}")
        assert completed.status_code == 200
        assert completed.json()["authenticated"] is True
        assert completed.json()["dated_games"] == 1
        assert "refresh_token" not in completed.json()

        db.expire_all()
        account = db.scalar(select(Account).where(Account.platform == Platform.steam))
        assert account is not None
        assert account.participant_id == participant.id
        assert account.account_id == profile.steam_id
        assert account.ownerships[0].owned_since.year == 2024
        assert account.ownerships[0].owned_since_source == "steam_license"
        assert account.ownerships[0].first_seen_is_baseline is True
        credentials = json.loads((tmp_path / "steam" / str(account.id) / "auth.json").read_text(encoding="utf-8"))
        assert credentials == {"steam_id": profile.steam_id, "refresh_token": "remember-me"}
        assert provider_auth_service.account_status(account)["connection_mode"] == "qr"
    finally:
        provider_auth_api._pending_steam_logins.clear()


def test_steam_openid_url_uses_official_endpoint_and_callback():
    callback = "https://games.example/api/provider-auth/steam/openid/callback?state=test-state"
    login_url = steam_openid.build_steam_openid_url(callback, "https://games.example/")
    parsed = urlparse(login_url)
    query = parse_qs(parsed.query)

    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == steam_openid.STEAM_OPENID_ENDPOINT
    assert query["openid.mode"] == ["checkid_setup"]
    assert query["openid.return_to"] == [callback]
    assert query["openid.realm"] == ["https://games.example/"]


def test_steam_openid_verifies_response_with_steam(monkeypatch):
    callback = "https://games.example/api/provider-auth/steam/openid/callback?state=test-state"
    claimed_id = "https://steamcommunity.com/openid/id/76561198000000007"
    captured: dict = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["data"] = kwargs["data"]
        return FakeResponse(text="ns:http://specs.openid.net/auth/2.0\nis_valid:true\n")

    monkeypatch.setattr(steam_openid.httpx, "post", fake_post)
    steam_id = steam_openid.verify_steam_openid_response(
        {
            "openid.ns": steam_openid.OPENID_NAMESPACE,
            "openid.mode": "id_res",
            "openid.op_endpoint": steam_openid.STEAM_OPENID_ENDPOINT,
            "openid.return_to": callback,
            "openid.claimed_id": claimed_id,
            "openid.identity": claimed_id,
            "openid.response_nonce": "2026-09-21T10:00:00Ztest",
            "openid.signed": "signed,op_endpoint,claimed_id,identity,return_to,response_nonce",
            "openid.sig": "signed-by-steam",
        },
        callback,
    )

    assert steam_id == "76561198000000007"
    assert captured["url"] == steam_openid.STEAM_OPENID_ENDPOINT
    assert captured["data"]["openid.mode"] == "check_authentication"
    assert captured["data"]["openid.sig"] == "signed-by-steam"


def test_steam_openid_browser_login_connects_public_account(monkeypatch, client, db, tmp_path):
    participant = Participant(nickname="Ada", present=True)
    db.add(participant)
    db.commit()
    profile = SteamProfile(
        steam_id="76561198000000008",
        display_name="AdaSteam",
        profile_url="https://steamcommunity.com/profiles/76561198000000008/",
        avatar_url=None,
        library_accessible=True,
        game_count=88,
    )
    monkeypatch.setattr(settings, "provider_auth_root", str(tmp_path))
    monkeypatch.setattr(provider_auth_api, "resolve_steam_profile", lambda reference: profile)
    monkeypatch.setattr(
        provider_auth_api,
        "verify_steam_openid_response",
        lambda params, expected_return_to: profile.steam_id,
    )
    provider_auth_api._pending_steam_openid.clear()

    try:
        started = client.post(
            "/api/provider-auth/steam/openid/start",
            json={
                "participant_id": participant.id,
                "origin": "http://testserver",
                "return_path": "/logins",
            },
        )
        assert started.status_code == 200
        login_query = parse_qs(urlparse(started.json()["login_url"]).query)
        callback_url = login_query["openid.return_to"][0]
        state = parse_qs(urlparse(callback_url).query)["state"][0]

        completed = client.get(
            "/api/provider-auth/steam/openid/callback",
            params={"state": state, "openid.mode": "id_res"},
            follow_redirects=False,
        )
        assert completed.status_code == 303
        redirect = urlparse(completed.headers["location"])
        assert f"{redirect.scheme}://{redirect.netloc}{redirect.path}" == "http://testserver/logins"
        assert parse_qs(redirect.query)["steam_openid"] == ["success"]

        db.expire_all()
        account = db.scalar(select(Account).where(Account.platform == Platform.steam))
        assert account is not None
        assert account.participant_id == participant.id
        assert account.account_id == profile.steam_id
        assert provider_auth_service.account_status(account)["connection_mode"] == "community"
    finally:
        provider_auth_api._pending_steam_openid.clear()


def test_steam_openid_rejects_unrelated_return_origin(client, db):
    participant = Participant(nickname="Ada", present=True)
    db.add(participant)
    db.commit()

    response = client.post(
        "/api/provider-auth/steam/openid/start",
        json={
            "participant_id": participant.id,
            "origin": "https://attacker.example",
            "return_path": "/logins",
        },
    )

    assert response.status_code == 400
    assert "Rücksprungadresse" in response.json()["detail"]
