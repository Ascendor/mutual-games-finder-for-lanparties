from io import BytesIO
import zipfile

import pytest

from app.core.config import settings
from app.services.archive_safety import validate_archive_members


def _archive(entries: dict[str, bytes]) -> zipfile.ZipFile:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    buffer.seek(0)
    return zipfile.ZipFile(buffer)


def test_archive_validation_accepts_expected_members(monkeypatch):
    monkeypatch.setattr(settings, "import_archive_max_members", 10)
    monkeypatch.setattr(settings, "import_archive_max_member_bytes", 1024)
    monkeypatch.setattr(settings, "import_archive_max_uncompressed_bytes", 2048)
    monkeypatch.setattr(settings, "import_archive_max_compression_ratio", 500.0)
    with _archive({"library/games.db": b"database", "covers/ignored.jpg": b"x" * 4096}) as archive:
        validate_archive_members(archive, ["library/games.db"], label="Testarchiv")


def test_archive_validation_rejects_too_many_entries(monkeypatch):
    monkeypatch.setattr(settings, "import_archive_max_members", 1)
    with _archive({"one.json": b"{}", "two.json": b"{}"}) as archive:
        with pytest.raises(ValueError, match="zu viele Dateien"):
            validate_archive_members(archive, ["one.json"], label="Testarchiv")


def test_archive_validation_rejects_large_relevant_member(monkeypatch):
    monkeypatch.setattr(settings, "import_archive_max_members", 10)
    monkeypatch.setattr(settings, "import_archive_max_member_bytes", 16)
    with _archive({"library/games.db": b"x" * 32}) as archive:
        with pytest.raises(ValueError, match="groesser als erlaubt"):
            validate_archive_members(archive, ["library/games.db"], label="Testarchiv")


def test_archive_validation_rejects_implausible_compression(monkeypatch):
    monkeypatch.setattr(settings, "import_archive_max_members", 10)
    monkeypatch.setattr(settings, "import_archive_max_member_bytes", 4096)
    monkeypatch.setattr(settings, "import_archive_max_uncompressed_bytes", 4096)
    monkeypatch.setattr(settings, "import_archive_max_compression_ratio", 2.0)
    with _archive({"library/games.db": b"0" * 2048}) as archive:
        with pytest.raises(ValueError, match="Kompressionsverhaeltnis"):
            validate_archive_members(archive, ["library/games.db"], label="Testarchiv")
