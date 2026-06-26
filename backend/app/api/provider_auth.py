from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Account
from app.services import provider_auth

router = APIRouter()


class ProviderCodePayload(BaseModel):
    code: str = ""
    email: str | None = None
    password: str | None = None
    two_factor_code: str | None = None
    access_token: str | None = None
    cookie: str | None = None
    pid: str | None = None


def _get_account(db: Session, account_id: int) -> Account:
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(404, "account not found")
    return account


@router.get("/status")
def auth_status(db: Session = Depends(get_db)):
    return provider_auth.status(db)


@router.get("/accounts/{account_id}/status")
def account_auth_status(account_id: int, db: Session = Depends(get_db)):
    account = _get_account(db, account_id)
    try:
        return provider_auth.account_status(account)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/accounts/{account_id}/start")
def start_login(account_id: int, db: Session = Depends(get_db)):
    account = _get_account(db, account_id)
    try:
        return provider_auth.start(account)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/accounts/{account_id}/complete")
def complete_login(account_id: int, payload: ProviderCodePayload, db: Session = Depends(get_db)):
    account = _get_account(db, account_id)
    try:
        return provider_auth.complete(account, payload.code.strip(), payload.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/accounts/{account_id}/logout")
def logout(account_id: int, db: Session = Depends(get_db)):
    account = _get_account(db, account_id)
    try:
        return provider_auth.logout(account)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc


