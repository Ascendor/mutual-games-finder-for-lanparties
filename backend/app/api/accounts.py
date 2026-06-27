from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Account, Platform
from app.schemas import AccountCreate, AccountRead, AccountUpdate

router = APIRouter()
LOCAL_ID_PLATFORMS = {Platform.epic, Platform.gog, Platform.ubisoft, Platform.xbox, Platform.ea}


def _platform_value(platform: Platform | str) -> str:
    return platform.value if isinstance(platform, Platform) else str(platform)


def _local_account_id(platform: Platform | str, participant_id: int, sequence: int) -> str:
    return f"local-{_platform_value(platform)}-{participant_id}-{sequence}"


def _repair_blank_provider_account_ids(db: Session) -> None:
    changed = False
    accounts = db.scalars(select(Account).where(Account.platform.in_(LOCAL_ID_PLATFORMS))).all()
    for account in accounts:
        if account.account_id:
            continue
        sibling_ids = {
            item.account_id
            for item in accounts
            if item.participant_id == account.participant_id and item.platform == account.platform and item.account_id
        }
        sequence = 1
        candidate = _local_account_id(account.platform, account.participant_id, sequence)
        while candidate in sibling_ids:
            sequence += 1
            candidate = _local_account_id(account.platform, account.participant_id, sequence)
        account.account_id = candidate
        if not account.display_name:
            account.display_name = _platform_value(account.platform).title()
        changed = True
    if changed:
        db.commit()


@router.get("", response_model=list[AccountRead])
def list_accounts(db: Session = Depends(get_db)):
    _repair_blank_provider_account_ids(db)
    return db.scalars(select(Account).order_by(Account.platform, Account.display_name)).all()


@router.post("", response_model=AccountRead, status_code=201)
def create_account(payload: AccountCreate, db: Session = Depends(get_db)):
    _repair_blank_provider_account_ids(db)
    data = payload.model_dump()
    existing = db.scalar(
        select(Account).where(
            Account.participant_id == data["participant_id"],
            Account.platform == data["platform"],
        )
    )
    if existing:
        if data.get("account_id") and (
            existing.account_id.startswith(f"local-{_platform_value(existing.platform)}-")
            or existing.account_id.startswith("playnite:")
        ):
            existing.account_id = data["account_id"]
        if data.get("display_name"):
            existing.display_name = data["display_name"]
        db.commit()
        db.refresh(existing)
        return existing
    if data["platform"] in LOCAL_ID_PLATFORMS and not data.get("account_id"):
        data["account_id"] = _local_account_id(data["platform"], data["participant_id"], 1)
    if not data.get("display_name"):
        data["display_name"] = _platform_value(data["platform"]).title()
    account = Account(**data)
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@router.patch("/{account_id}", response_model=AccountRead)
def update_account(account_id: int, payload: AccountUpdate, db: Session = Depends(get_db)):
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(404, "account not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(account, key, value)
    db.commit()
    db.refresh(account)
    return account


@router.delete("/{account_id}", status_code=204)
def delete_account(account_id: int, db: Session = Depends(get_db)):
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(404, "account not found")
    db.delete(account)
    db.commit()

