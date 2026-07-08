from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter()


class AdminUnlockRequest(BaseModel):
    password: str


class AdminUnlockResponse(BaseModel):
    unlocked: bool


@router.post("/unlock", response_model=AdminUnlockResponse)
def unlock_admin(payload: AdminUnlockRequest) -> AdminUnlockResponse:
    if not settings.admin_password:
        raise HTTPException(status_code=503, detail="admin password is not configured")
    if payload.password != settings.admin_password:
        raise HTTPException(status_code=401, detail="invalid admin password")
    return AdminUnlockResponse(unlocked=True)
