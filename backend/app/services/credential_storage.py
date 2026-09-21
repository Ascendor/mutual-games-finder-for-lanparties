from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4


def ensure_private_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def write_private_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_private_directory(path.parent)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)
