import pytest

from app.core.config import settings
from app.models import Platform
from app.services.provider_policy import provider_integration_enabled, require_provider_integration


def test_documented_providers_remain_enabled(monkeypatch):
    monkeypatch.setattr(settings, "unofficial_provider_integrations_enabled", False)

    assert provider_integration_enabled(Platform.steam) is True
    assert provider_integration_enabled(Platform.xbox) is True


def test_unofficial_providers_are_opt_in(monkeypatch):
    monkeypatch.setattr(settings, "unofficial_provider_integrations_enabled", False)

    assert provider_integration_enabled(Platform.ea) is False
    with pytest.raises(ValueError, match="inoffizielle Provider-Anbindung"):
        require_provider_integration(Platform.ea)

    monkeypatch.setattr(settings, "unofficial_provider_integrations_enabled", True)
    assert provider_integration_enabled(Platform.ea) is True


def test_provider_availability_api_marks_unofficial_providers_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "unofficial_provider_integrations_enabled", False)

    response = client.get("/api/provider-auth/availability")

    assert response.status_code == 200
    availability = {item["platform"]: item for item in response.json()}
    assert availability["steam"] == {
        "platform": "steam",
        "enabled": True,
        "experimental": False,
    }
    assert availability["ea"] == {
        "platform": "ea",
        "enabled": False,
        "experimental": True,
    }
