from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import PlayniteImportRead
from app.services.playnite_import import import_playnite_export

router = APIRouter()


@router.post("/playnite", response_model=PlayniteImportRead)
async def import_playnite(
    participant_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    content = await file.read()
    return import_playnite_export(db, participant_id, content)
