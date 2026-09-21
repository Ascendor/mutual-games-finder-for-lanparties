import json
import stat

from app.services.credential_storage import write_private_json


def test_private_json_is_atomic_and_restricts_permissions(tmp_path):
    path = tmp_path / "provider" / "auth.json"

    write_private_json(path, {"access_token": "first"})
    write_private_json(path, {"access_token": "second"})

    assert json.loads(path.read_text(encoding="utf-8")) == {"access_token": "second"}
    assert list(path.parent.glob(".*.tmp")) == []
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
