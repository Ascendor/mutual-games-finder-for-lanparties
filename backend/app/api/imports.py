from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models import Participant, SyncRun
from app.schemas import SyncRunRead
from app.services.gog_galaxy_import import create_gog_galaxy_import_run, run_gog_galaxy_import
from app.services.playnite_import import create_playnite_import_run, run_playnite_import

router = APIRouter()
UPLOAD_CHUNK_SIZE = 8 * 1024 * 1024


def remove_stale_uploads() -> None:
    upload_dir = Path(settings.playnite_upload_dir)
    if not upload_dir.is_dir():
        return
    for prefix in ("playnite-*", "gog-galaxy-*"):
        for path in upload_dir.glob(prefix):
            if path.is_file():
                path.unlink(missing_ok=True)


async def _store_upload(file: UploadFile, *, prefix: str, default_suffix: str, label: str) -> Path:
    upload_dir = Path(settings.playnite_upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    upload_dir.chmod(0o700)
    filename = str(file.filename or "").casefold()
    suffix = Path(filename).suffix
    if suffix not in {".db", ".sqlite", ".sqlite3", ".zip", ".json"}:
        suffix = default_suffix
    path: Path | None = None
    total_bytes = 0
    try:
        with NamedTemporaryFile(dir=upload_dir, prefix=prefix, suffix=suffix, delete=False) as target:
            path = Path(target.name)
            while chunk := await file.read(UPLOAD_CHUNK_SIZE):
                total_bytes += len(chunk)
                if total_bytes > settings.playnite_upload_max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=f"{label} ueberschreitet das Uploadlimit von {settings.playnite_upload_max_bytes} Bytes.",
                    )
                target.write(chunk)
        path.chmod(0o600)
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
            detail=f"{label} konnte nicht temporaer gespeichert werden.",
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
    path = await _store_upload(file, prefix="playnite-", default_suffix=".zip", label="Playnite-Backup")
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


@router.post("/gog-galaxy", response_model=SyncRunRead, status_code=202)
async def import_gog_galaxy(
    background_tasks: BackgroundTasks,
    participant_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not db.get(Participant, participant_id):
        raise HTTPException(404, "participant not found")
    path = await _store_upload(file, prefix="gog-galaxy-", default_suffix=".db", label="GOG-Galaxy-Import")
    try:
        run = create_gog_galaxy_import_run(db, participant_id, file.filename or "GOG-Galaxy-Datenbank")
    except RuntimeError as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(409, str(exc)) from exc
    except Exception:
        path.unlink(missing_ok=True)
        raise
    background_tasks.add_task(run_gog_galaxy_import, run.id, path)
    return run


@router.get("/playnite/{run_id}", response_model=SyncRunRead)
def playnite_import_status(run_id: int, db: Session = Depends(get_db)):
    run = db.get(SyncRun, run_id)
    if not run or run.kind != "playnite":
        raise HTTPException(404, "Playnite-Import nicht gefunden")
    return run


@router.get("/gog-galaxy/{run_id}", response_model=SyncRunRead)
def gog_galaxy_import_status(run_id: int, db: Session = Depends(get_db)):
    run = db.get(SyncRun, run_id)
    if not run or run.kind != "gog_galaxy":
        raise HTTPException(404, "GOG-Galaxy-Import nicht gefunden")
    return run
