from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models import Participant, SyncRun
from app.schemas import SyncRunRead
from app.services.playnite_import import create_playnite_import_run, run_playnite_import

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


@router.post("/playnite", response_model=SyncRunRead, status_code=202)
async def import_playnite(
    background_tasks: BackgroundTasks,
    participant_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not db.get(Participant, participant_id):
        raise HTTPException(404, "participant not found")
    path = await _store_upload(file)
    try:
        run = create_playnite_import_run(db, participant_id, file.filename or "Playnite-Backup")
    except RuntimeError as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(409, str(exc)) from exc
    except Exception:
        path.unlink(missing_ok=True)
        raise
    background_tasks.add_task(run_playnite_import, run.id, path)
    return run


@router.get("/playnite/{run_id}", response_model=SyncRunRead)
def playnite_import_status(run_id: int, db: Session = Depends(get_db)):
    run = db.get(SyncRun, run_id)
    if not run or run.kind != "playnite":
        raise HTTPException(404, "Playnite-Import nicht gefunden")
    return run
