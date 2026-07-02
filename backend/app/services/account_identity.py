from __future__ import annotations

from typing import Any

from app.models import Account, Platform

PLATFORM_DISPLAY_NAMES = {
    "amazon": "amazon games",
    "battle_net": "battle.net",
    "ea": "ea app",
    "epic": "epic games",
    "gog": "gog",
    "humble": "humble",
    "meta": "meta / oculus",
    "steam": "steam",
    "ubisoft": "ubisoft connect",
    "xbox": "xbox live",
}


def platform_value(platform: Platform | str) -> str:
    return platform.value if isinstance(platform, Platform) else str(platform)


def is_placeholder_display_name(account: Account) -> bool:
    value = (account.display_name or "").strip().casefold()
    platform_key = platform_value(account.platform).casefold()
    platform = platform_key.replace("_", " ")
    return (
        not value
        or value in {platform, PLATFORM_DISPLAY_NAMES.get(platform_key, platform)}
        or value.replace(" ", "_") == platform_key
        or value.startswith("playnite ")
        or value.endswith(" (playnite)")
        or value.endswith(" (teilnehmer)")
    )


def apply_account_identity(
    account: Account,
    identity: dict[str, Any] | None = None,
    *,
    participant_fallback: bool = False,
) -> bool:
    identity = identity or {}
    changed = False
    provider_account_id = str(identity.get("provider_account_id") or "").strip()
    provider_display_name = str(identity.get("provider_display_name") or "").strip()

    current_id = str(account.account_id or "")
    if provider_account_id and (
        not current_id
        or current_id.startswith("local-")
        or current_id.startswith("playnite:")
    ):
        account.account_id = provider_account_id
        changed = True

    if provider_display_name and account.display_name != provider_display_name:
        account.display_name = provider_display_name
        changed = True
    elif participant_fallback and is_placeholder_display_name(account):
        nickname = str(getattr(account.participant, "nickname", "") or "").strip()
        fallback_name = f"{nickname} (Teilnehmer)" if nickname else ""
        if fallback_name and account.display_name != fallback_name:
            account.display_name = fallback_name
            changed = True

    return changed
