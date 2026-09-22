from fastapi import APIRouter

from app.core.config import settings
from app.schemas import AppConfigRead


router = APIRouter()


@router.get("", response_model=AppConfigRead)
def public_app_config():
    return {
        "display_name": settings.app_display_name,
        "title": settings.app_title,
        "subtitle": settings.app_subtitle,
        "source_url": settings.app_source_url,
        "upstream_source_url": settings.upstream_source_url,
    }
