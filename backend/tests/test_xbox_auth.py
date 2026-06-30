import json

from app.models import Account, Platform
from app.services import xbox_auth


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.is_success = 200 <= status_code < 300

    def json(self):
        return self.payload


def xbox_account():
    return Account(id=17, participant_id=3, platform=Platform.xbox, account_id="local-xbox-3-1")


def test_start_device_login_persists_pending_flow(monkeypatch, tmp_path):
    monkeypatch.setattr(xbox_auth.settings, "provider_auth_root", str(tmp_path))
    monkeypatch.setattr(xbox_auth.settings, "xbox_client_id", "client-id")
    monkeypatch.setattr(
        xbox_auth.httpx,
        "post",
        lambda *args, **kwargs: FakeResponse(
            {
                "device_code": "device-secret",
                "user_code": "ABCD-EFGH",
                "verification_uri": "https://www.microsoft.com/link",
                "expires_in": 900,
                "interval": 5,
            }
        ),
    )

    result = xbox_auth.start_device_login(xbox_account())
    stored = json.loads((tmp_path / "xbox" / "17" / "auth.json").read_text(encoding="utf-8"))

    assert result["user_code"] == "ABCD-EFGH"
    assert result["login_url"] == "https://www.microsoft.com/link"
    assert stored["device_flow"]["device_code"] == "device-secret"


def test_poll_device_login_reports_pending(monkeypatch, tmp_path):
    monkeypatch.setattr(xbox_auth.settings, "provider_auth_root", str(tmp_path))
    monkeypatch.setattr(xbox_auth.settings, "xbox_client_id", "client-id")
    xbox_auth._save(
        17,
        {
            "device_flow": {
                "device_code": "device-secret",
                "expires_at": xbox_auth.time.time() + 900,
                "interval": 5,
            }
        },
    )
    monkeypatch.setattr(
        xbox_auth.httpx,
        "post",
        lambda *args, **kwargs: FakeResponse({"error": "authorization_pending"}, status_code=400),
    )

    result = xbox_auth.poll_device_login(xbox_account())

    assert result["pending"] is True
    assert result["authenticated"] is False


def test_poll_device_login_exchanges_and_stores_xbox_credentials(monkeypatch, tmp_path):
    monkeypatch.setattr(xbox_auth.settings, "provider_auth_root", str(tmp_path))
    monkeypatch.setattr(xbox_auth.settings, "xbox_client_id", "client-id")
    xbox_auth._save(
        17,
        {
            "device_flow": {
                "device_code": "device-secret",
                "expires_at": xbox_auth.time.time() + 900,
                "interval": 5,
            }
        },
    )

    def fake_post(url, **kwargs):
        if url == xbox_auth.TOKEN_URL:
            return FakeResponse(
                {
                    "access_token": "microsoft-token",
                    "refresh_token": "refresh-token",
                    "expires_in": 3600,
                    "scope": xbox_auth.XBOX_SCOPES,
                }
            )
        if url == xbox_auth.XBOX_USER_AUTH_URL:
            assert kwargs["json"]["Properties"]["RpsTicket"] == "d=microsoft-token"
            return FakeResponse({"Token": "xbox-user-token"})
        if url == xbox_auth.XSTS_AUTH_URL:
            assert kwargs["json"]["Properties"]["UserTokens"] == ["xbox-user-token"]
            return FakeResponse(
                {
                    "Token": "xsts-token",
                    "NotAfter": "2099-01-01T00:00:00Z",
                    "DisplayClaims": {
                        "xui": [{"uhs": "user-hash", "xid": "123456", "gtg": "LANPlayer"}]
                    },
                }
            )
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(xbox_auth.httpx, "post", fake_post)

    result = xbox_auth.poll_device_login(xbox_account())
    stored = json.loads((tmp_path / "xbox" / "17" / "auth.json").read_text(encoding="utf-8"))

    assert result["authenticated"] is True
    assert result["xuid"] == "123456"
    assert result["gamertag"] == "LANPlayer"
    assert stored["xsts_token"] == "xsts-token"
    assert stored["oauth_refresh_token"] == "refresh-token"
    assert "device_flow" not in stored
