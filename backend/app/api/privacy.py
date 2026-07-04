from fastapi import APIRouter

from app.core.config import settings
from app.schemas import PrivacyInfoRead


router = APIRouter()


@router.get("", response_model=PrivacyInfoRead)
def privacy_information():
    return {
        "controller_name": settings.privacy_controller_name,
        "controller_contact": settings.privacy_controller_contact,
        "hosting_provider": settings.privacy_hosting_provider,
        "analytics_retention_days": settings.analytics_retention_days,
        "access_log_retention_days": settings.privacy_access_log_retention_days,
        "backup_retention_days": settings.privacy_backup_retention_days,
        "supervisory_authority": settings.privacy_supervisory_authority,
        "supervisory_authority_url": settings.privacy_supervisory_authority_url,
    }
