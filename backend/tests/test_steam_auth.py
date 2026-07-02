from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import provider_auth as provider_auth_api
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Account, Participant, Platform
from app.services import steam_auth
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


def test_verify_steam_openid_checks_response_with_steam(monkeypatch):
    monkeypatch.setattr(
        steam_auth.httpx,
        "post",
        lambda *args, **kwargs: FakeResponse(text="ns:http://specs.openid.net/auth/2.0\nis_valid:true\n"),
    )
    steam_id = steam_auth.verify_steam_openid(
        {
            "openid.ns": steam_auth.STEAM_OPENID_NAMESPACE,
            "openid.mode": "id_res",
            "openid.op_endpoint": steam_auth.STEAM_OPENID_ENDPOINT,
            "openid.claimed_id": "https://steamcommunity.com/openid/id/76561198000000003",
            "openid.identity": "https://steamcommunity.com/openid/id/76561198000000003",
            "openid.return_to": "https://play.example/api/provider-auth/steam/callback",
        }
    )
    assert steam_id == "76561198000000003"


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


def test_steam_openid_callback_creates_account(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    db = Session()
    participant = Participant(nickname="Ada", present=True)
    db.add(participant)
    db.commit()

    def override_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    profile = SteamProfile(
        steam_id="76561198000000006",
        display_name="AdaSteam",
        profile_url="https://steamcommunity.com/profiles/76561198000000006/",
        avatar_url=None,
        library_accessible=True,
        game_count=99,
    )
    monkeypatch.setattr(settings, "cors_origins", "https://play.example")
    monkeypatch.setattr(provider_auth_api, "verify_steam_openid", lambda params: profile.steam_id)
    monkeypatch.setattr(provider_auth_api, "resolve_steam_profile", lambda reference: profile)
    provider_auth_api._pending_steam_logins.clear()
    app.dependency_overrides[get_db] = override_db

    try:
        client = TestClient(app)
        start = client.post(
            "/api/provider-auth/steam/start",
            json={"participant_id": participant.id, "origin": "https://play.example"},
        )
        assert start.status_code == 200
        payload = start.json()
        query = parse_qs(urlparse(payload["login_url"]).query)
        assert query["openid.return_to"][0].startswith(
            "https://play.example/api/provider-auth/steam/callback?state="
        )

        callback = client.get(
            "/api/provider-auth/steam/callback",
            params={"state": payload["state"], "openid.mode": "id_res"},
        )
        assert callback.status_code == 200
        assert "steam-login-result" in callback.text
        assert '"success": true' in callback.text

        check = Session()
        try:
            account = check.scalar(select(Account).where(Account.platform == Platform.steam))
            assert account is not None
            assert account.participant_id == participant.id
            assert account.account_id == profile.steam_id
        finally:
            check.close()
    finally:
        provider_auth_api._pending_steam_logins.clear()
        app.dependency_overrides.clear()
        db.close()
