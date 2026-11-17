"""login.py writes `<phone>.jsession` files (the owner's cross-project session
format); config.py's SESSION_FILE reads the session and client fingerprint
back from one."""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from telemirror.misc.jsession import TDESKTOP_APP, load_jsession, save_jsession

REPO_ROOT = Path(__file__).resolve().parent.parent

ME = SimpleNamespace(
    first_name="Test", last_name=None, id=42, phone="79990000000", username="tester"
)


def test_save_writes_the_shared_layout_owner_only(tmp_path):
    path = tmp_path / "sessions" / "79990000000.jsession"
    save_jsession(str(path), "1AAAA", ME, TDESKTOP_APP)

    data = json.loads(path.read_text())
    assert list(data) == [
        "auth_key", "account", "application", "proxy", "password", "registered_at"
    ]
    assert list(data["account"]) == [
        "first_name", "last_name", "user_id", "added_at", "phone_number", "username"
    ]
    assert data["auth_key"] == "1AAAA"
    assert data["account"]["user_id"] == 42
    assert data["account"]["phone_number"] == "79990000000"
    assert data["application"] == TDESKTOP_APP
    assert data["proxy"] is None and data["password"] is None
    assert data["registered_at"] is None
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_save_backs_up_an_existing_file_instead_of_overwriting(tmp_path):
    path = tmp_path / "s.jsession"
    path.write_text('{"auth_key": "OLD"}')
    path.chmod(0o644)

    backup = save_jsession(str(path), "1NEW", ME, TDESKTOP_APP)

    assert backup is not None and backup.endswith(".bak")
    assert json.loads(Path(backup).read_text())["auth_key"] == "OLD"
    assert json.loads(path.read_text())["auth_key"] == "1NEW"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_save_without_existing_file_makes_no_backup(tmp_path):
    assert save_jsession(str(tmp_path / "s.jsession"), "1AAAA", ME, TDESKTOP_APP) is None


def test_load_round_trips(tmp_path):
    path = tmp_path / "s.jsession"
    save_jsession(str(path), "1AAAA", ME, TDESKTOP_APP)
    data = load_jsession(str(path))
    assert data["auth_key"] == "1AAAA"
    assert data["application"]["api_id"] == 2040


@pytest.mark.parametrize(
    "content",
    [
        {"application": TDESKTOP_APP},
        {"auth_key": "1AAAA", "application": {"api_id": 2040}},
        {"auth_key": "1AAAA"},
    ],
)
def test_load_rejects_incomplete_file_naming_the_path(tmp_path, content):
    path = tmp_path / "bad.jsession"
    path.write_text(json.dumps(content))
    with pytest.raises(ValueError, match="bad.jsession"):
        load_jsession(str(path))


def _config_values(session_file: str, cwd: Path) -> list:
    """Import config.py in a fresh interpreter (it resolves everything at
    import time) with SESSION_FILE set and no API_ID/API_HASH/SESSION_STRING."""
    env = {
        k: v for k, v in os.environ.items()
        if k not in ("API_ID", "API_HASH", "SESSION_STRING")
    }
    env.update(
        SESSION_FILE=session_file,
        USE_MEMORY_DB="true",
        YAML_CONFIG_ENV="directions:\n  - from: [-1001]\n    to: [-1002]\n",
        PYTHONPATH=str(REPO_ROOT),
    )
    out = subprocess.run(
        [sys.executable, "-c", (
            "import json, config as c; print(json.dumps([c.SESSION_STRING, c.API_ID, "
            "c.API_HASH, c.API_DEVICE_MODEL, c.API_SYSTEM_VERSION, c.API_APP_VERSION, "
            "c.API_LANG_PACK, c.API_SYSTEM_LANG_CODE]))"
        )],
        cwd=cwd, env=env, capture_output=True, text=True, check=True,
    ).stdout
    return json.loads(out.strip().splitlines()[-1])


def test_config_takes_session_and_fingerprint_from_session_file(tmp_path):
    path = tmp_path / "s.jsession"
    save_jsession(str(path), "1AAAA", ME, TDESKTOP_APP)
    assert _config_values(str(path), cwd=REPO_ROOT) == [
        "1AAAA", 2040, TDESKTOP_APP["api_hash"], "PC 64bit",
        "Linux dwm X11 glibc 2.32", "3.7.3 x64", "tdesktop", "cs",
    ]


def test_relative_session_file_resolves_from_repo_root_not_cwd(tmp_path):
    path = tmp_path / "s.jsession"
    save_jsession(str(path), "1AAAA", ME, TDESKTOP_APP)
    relative = os.path.relpath(path, REPO_ROOT)
    other_cwd = tmp_path / "elsewhere"
    other_cwd.mkdir()
    assert _config_values(relative, cwd=other_cwd)[0] == "1AAAA"
