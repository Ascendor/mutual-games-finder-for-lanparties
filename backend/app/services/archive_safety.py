from __future__ import annotations

import zipfile
from collections.abc import Iterable

from app.core.config import settings


def validate_archive_members(
    archive: zipfile.ZipFile,
    member_names: Iterable[str],
    *,
    label: str,
) -> None:
    infos = archive.infolist()
    if len(infos) > settings.import_archive_max_members:
        raise ValueError(
            f"{label} enthaelt zu viele Dateien ({len(infos)}; erlaubt sind "
            f"{settings.import_archive_max_members})."
        )

    info_by_name = {info.filename: info for info in infos}
    selected = [info_by_name[name] for name in dict.fromkeys(member_names) if name in info_by_name]
    total_size = 0
    for info in selected:
        if info.is_dir():
            continue
        if info.file_size < 0 or info.compress_size < 0:
            raise ValueError(f"{label} enthaelt einen ungueltigen ZIP-Eintrag.")
        if info.file_size > settings.import_archive_max_member_bytes:
            raise ValueError(
                f"{label}: {info.filename} ist entpackt groesser als erlaubt "
                f"({settings.import_archive_max_member_bytes} Bytes)."
            )
        if info.file_size and (
            info.compress_size == 0
            or info.file_size / info.compress_size > settings.import_archive_max_compression_ratio
        ):
            raise ValueError(
                f"{label}: {info.filename} hat ein unplausibles Kompressionsverhaeltnis."
            )
        total_size += info.file_size
        if total_size > settings.import_archive_max_uncompressed_bytes:
            raise ValueError(
                f"{label} ist entpackt groesser als erlaubt "
                f"({settings.import_archive_max_uncompressed_bytes} Bytes)."
            )
