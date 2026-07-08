from app.core.config import settings


def test_admin_unlock_requires_configured_password(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_password", None)

    response = client.post("/api/admin/unlock", json={"password": "anything"})

    assert response.status_code == 503


def test_admin_unlock_rejects_wrong_password(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_password", "secret")

    response = client.post("/api/admin/unlock", json={"password": "wrong"})

    assert response.status_code == 401


def test_admin_unlock_accepts_configured_password(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_password", "secret")

    response = client.post("/api/admin/unlock", json={"password": "secret"})

    assert response.status_code == 200
    assert response.json() == {"unlocked": True}
