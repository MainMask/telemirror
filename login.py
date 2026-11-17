"""
Telegram login: saves the session as sessions/<phone>.jsession. Point
SESSION_FILE at it in .env (or pick it as a project's account in the panel).

    python login.py                 # sign in by phone (Telegram Desktop fingerprint)
    python login.py --import PATH   # an account already signed in elsewhere: a tdata
                                    # folder or its ZIP, a .session (its .json next to
                                    # it is read too) or a ZIP of those
"""

import argparse
import asyncio
import getpass
import shutil
import sys
import tempfile
from pathlib import Path

from telethon.sessions import StringSession

from telemirror.misc import session_import
from telemirror.misc.jsession import TDESKTOP_APP, save_jsession
from telemirror.misc.telegram_client import apply_lang_pack
from telemirror.projects import REPO_DIR, SESSIONS_DIR


def sign_in() -> str:
    from telethon.sync import TelegramClient  # patches Telethon for sync calls: only here

    client = TelegramClient(
        StringSession(),
        TDESKTOP_APP["api_id"],
        TDESKTOP_APP["api_hash"],
        device_model=TDESKTOP_APP["device_name"],
        system_version=TDESKTOP_APP["sdk"],
        app_version=TDESKTOP_APP["app_version"],
        system_lang_code=TDESKTOP_APP["system_lang_code"],
    )
    apply_lang_pack(client, TDESKTOP_APP["lang_pack"])

    # Entering the block runs start(): prompts for phone, code and (if enabled)
    # the 2FA password; the password is never stored.
    with client:
        me = client.get_me()
        relpath = f"sessions/{me.phone}.jsession"
        backup = save_jsession(str(REPO_DIR / relpath), client.session.save(), me, TDESKTOP_APP)

    if backup:
        print(f"Previous session kept as: {backup} (still active until terminated in Telegram settings)")
    return relpath


def import_account(source: Path) -> str:
    """The one account in ``source`` (a folder, a ZIP or a .session), checked and saved."""
    with tempfile.TemporaryDirectory(prefix="session-import-") as tmp:
        if source.is_dir():
            root = str(source)
        elif source.suffix.lower() == ".zip":
            session_import.unpack(source.read_bytes(), tmp)
            root = tmp
        elif source.suffix.lower() == ".session":
            for path in (source, source.with_suffix(".json")):
                if path.exists():
                    shutil.copy(path, tmp)
            root = tmp
        else:
            raise session_import.SessionImportError("нужна папка, ZIP или файл .session")
        passcode = None
        while True:
            try:
                saved = asyncio.run(session_import.import_folder(root, SESSIONS_DIR, passcode))
                return str(saved.relative_to(REPO_DIR))
            except session_import.NeedPasscode as e:
                passcode = getpass.getpass(f"{e}. Telegram Desktop passcode: ")


def main() -> None:
    parser = argparse.ArgumentParser(description="Save a Telegram account as sessions/<phone>.jsession")
    parser.add_argument("--import", dest="source", type=Path, metavar="PATH",
                        help="tdata folder or ZIP, .session (+ .json), or a ZIP of those")
    args = parser.parse_args()
    if args.source is None:
        relpath = sign_in()
    else:
        try:
            relpath = import_account(args.source)
        except session_import.SessionImportError as e:
            sys.exit(f"Import failed: {e}")
    print(f"Session saved: {relpath}")
    print(f"Add to .env:   SESSION_FILE={relpath}")


if __name__ == "__main__":
    main()
