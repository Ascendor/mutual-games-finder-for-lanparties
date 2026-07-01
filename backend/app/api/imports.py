from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.schemas import PlayniteImportRead
from app.services.playnite_import import import_playnite_export_path

router = APIRouter()
UPLOAD_CHUNK_SIZE = 8 * 1024 * 1024


def remove_stale_uploads() -> None:
    upload_dir = Path(settings.playnite_upload_dir)
    if not upload_dir.is_dir():
        return
    for path in upload_dir.glob("playnite-*"):
        if path.is_file():
            path.unlink(missing_ok=True)


async def _store_upload(file: UploadFile) -> Path:
    upload_dir = Path(settings.playnite_upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    suffix = ".zip" if str(file.filename or "").casefold().endswith(".zip") else ".json"
    path: Path | None = None
    total_bytes = 0
    try:
        with NamedTemporaryFile(dir=upload_dir, prefix="playnite-", suffix=suffix, delete=False) as target:
            path = Path(target.name)
            while chunk := await file.read(UPLOAD_CHUNK_SIZE):
                total_bytes += len(chunk)
                if total_bytes > settings.playnite_upload_max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=f"Playnite-Backup überschreitet das Uploadlimit von {settings.playnite_upload_max_bytes} Bytes.",
                    )
                target.write(chunk)
        return path
    except HTTPException:
        if path:
            path.unlink(missing_ok=True)
        raise
    except OSError as exc:
        if path:
            path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail="Das Playnite-Backup konnte nicht temporär gespeichert werden.",
        ) from exc
    finally:
        await file.close()


@router.post("/playnite", response_model=PlayniteImportRead)
async def import_playnite(
    participant_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    path = await _store_upload(file)
    try:
        return import_playnite_export_path(db, participant_id, path)
    finally:
        path.unlink(missing_ok=True)
