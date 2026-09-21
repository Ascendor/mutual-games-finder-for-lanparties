from __future__ import annotations

from app.core.config import settings
from app.models import Platform


UNOFFICIAL_DIRECT_PROVIDERS = frozenset(
    {
        Platform.epic,
        Platform.gog,
        Platform.ubisoft,
        Platform.ea,
        Platform.amazon,
        Platform.battle_net,
        Platform.humble,
        Platform.meta,
    }
)


def provider_integration_enabled(platform: Platform | str) -> bool:
    value = platform if isinstance(platform, Platform) else Platform(str(platform))
    return value not in UNOFFICIAL_DIRECT_PROVIDERS or settings.unofficial_provider_integrations_enabled


def require_provider_integration(platform: Platform | str) -> None:
    if not provider_integration_enabled(platform):
        raise ValueError(
            "Diese inoffizielle Provider-Anbindung ist auf diesem Server deaktiviert. "
            "Die Bibliothek kann weiterhin ueber Playnite oder GOG Galaxy importiert werden."
        )
