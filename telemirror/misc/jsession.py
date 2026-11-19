"""``<phone>.jsession`` session files — the JSON layout shared with the
owner's other projects: a Telethon StringSession (``auth_key``), the account
it belongs to, and the client fingerprint (``application``) it was created
with, so every later connection presents the same app as the login did."""

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

# Telegram Desktop fingerprint new sessions are created with (telemirror.login).
TDESKTOP_APP: Dict[str, Any] = {
    "api_id": 2040,
    "api_hash": "b18441a1ff607e10a989891a5462e627",
    "device_name": "PC 64bit",
    "app_version": "3.7.3 x64",
    "sdk": "Linux dwm X11 glibc 2.32",
    "lang_pack": "tdesktop",
    "system_lang_code": "cs",
}


def load_jsession(path: str) -> Dict[str, Any]:
    """Read a ``.jsession`` file; fail with the path on a missing key."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    app = data.get("application") or {}
    if not data.get("auth_key") or not app.get("api_id") or not app.get("api_hash"):
        raise ValueError(
            f"{path}: not a valid .jsession file "
            f"(needs auth_key and application.api_id/api_hash)"
        )
    return data


def save_jsession(path: str, session_string: str, me, application: Dict[str, Any]) -> Optional[str]:
    """Write a ``.jsession`` file for the logged-in user ``me``, owner-only
    readable — ``auth_key`` is full access to the account.

    An existing file is renamed to ``<name>.<unix time>.bak`` first: its
    session is still live on Telegram's side, so silently overwriting it
    would lose the only copy of a working key. Returns the backup path."""
    data = {
        "auth_key": session_string,
        "account": {
            "first_name": me.first_name,
            "last_name": me.last_name,
            "user_id": me.id,
            "added_at": time.time(),
            "phone_number": me.phone,
            "username": me.username,
        },
        "application": dict(application),
        "proxy": None,
        "password": None,
        "registered_at": None,
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if os.path.exists(path):
        backup = f"{path}.{int(time.time())}.bak"
        os.rename(path, backup)
    # O_EXCL: the path was just freed, so the 0o600 mode always applies.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    return backup
