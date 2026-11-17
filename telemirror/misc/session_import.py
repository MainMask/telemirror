"""Accounts from other tools' session files (the ones teleharvester takes): a
ZIP of a Telegram Desktop ``tdata`` folder, a Telethon ``.session`` (SQLite)
with the ``.json`` sellers put next to it, or a ZIP of those; or a ``.jsession``
from another copy of this project. The account is
checked to be signed in, then saved as ``sessions/<phone>.jsession`` — the
format everything here runs on. One account per import: a project runs on one
session.

The key is taken as it is (no new sign-in), so no 2FA password is needed and
none is stored. ``opentele`` (tdata) patches Telethon's classes on import, so
it is only ever loaded in a short child process (``_TDATA_READER``).
"""

import asyncio
import io
import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

from telethon.sessions import SQLiteSession, StringSession

from telemirror.misc.jsession import TDESKTOP_APP, load_jsession, save_jsession
from telemirror.misc.telegram_client import build_telegram_client

MAX_UNZIPPED = 100 * 1024 * 1024  # a tdata folder is small: a ZIP mustn't fill the disk
CONNECT_TIMEOUT = 40  # connect + the authorization check of the imported key
TDATA_TIMEOUT = 60  # reading a tdata in the child process


class SessionImportError(ValueError):
    """Why the files can't be imported — a Russian sentence shown as is."""


class NeedPasscode(SessionImportError):
    """The tdata is encrypted with Telegram Desktop's local passcode (or the given one is wrong)."""


def unpack(data: bytes, into: str) -> None:
    """A ZIP into the folder ``into``."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if sum(info.file_size for info in archive.infolist()) > MAX_UNZIPPED:
                raise SessionImportError("архив слишком велик в распакованном виде")
            archive.extractall(into)  # strips absolute paths and "..": stays inside `into`
    except zipfile.BadZipFile:
        raise SessionImportError("это не ZIP-архив или он повреждён") from None


def find_tdata(root: str) -> list:
    """The tdata folders under ``root``: the ones holding ``key_datas``."""
    return sorted(dirpath for dirpath, _, filenames in os.walk(root) if "key_datas" in filenames)


def find_sessions(root: str) -> list:
    """[(a .session file, its .json's data or {})] under ``root``."""
    found = []
    for dirpath, _, filenames in os.walk(root):
        for name in sorted(filenames):
            if not name.endswith(".session"):
                continue
            try:
                with open(os.path.join(dirpath, name[: -len(".session")] + ".json"), encoding="utf-8-sig") as f:
                    meta = json.load(f)
            except (OSError, ValueError):  # none, or unreadable: the Telegram Desktop profile
                meta = {}
            found.append((os.path.join(dirpath, name), meta if isinstance(meta, dict) else {}))
    return found


def read_session_key(path: str) -> str:
    """The .session's key and data center as a StringSession; read from a copy
    (SQLiteSession writes to the file it opens)."""
    with tempfile.TemporaryDirectory() as tmp:
        copy = os.path.join(tmp, "account.session")
        shutil.copyfile(path, copy)
        try:
            session = SQLiteSession(copy)
        except Exception as e:  # noqa: BLE001 - sqlite3.DatabaseError and the like
            raise SessionImportError(f"файл .session не читается: {e}") from None
        try:
            if session.auth_key is None or not session.auth_key.key or not session.dc_id:
                raise SessionImportError("в файле .session нет ключа авторизации")
            return StringSession.save(session)
        finally:
            session.close()


def application_of(meta: dict) -> dict:
    """The app and device the account is presented with: the .json's (its keys
    as sellers write them), each missing one the Telegram Desktop profile's."""
    app = dict(TDESKTOP_APP)
    if not (meta.get("app_id") and meta.get("app_hash")):
        return app
    pairs = {"api_id": ("app_id",), "api_hash": ("app_hash",), "device_name": ("device", "device_model"),
             "app_version": ("app_version",), "sdk": ("sdk", "system_version"), "lang_pack": ("lang_pack",),
             "system_lang_code": ("system_lang_pack", "system_lang_code")}
    for key, names in pairs.items():
        value = next((meta[n] for n in names if meta.get(n)), None)
        if value is None:
            continue
        if key != "api_id":
            app[key] = str(value)
            continue
        try:
            app[key] = int(value)
        except (TypeError, ValueError):
            raise SessionImportError(f"в .json неверный app_id: {str(value)[:40]}") from None
    return app


def jsession_key(raw: bytes) -> tuple[str, dict]:
    """An uploaded ``.jsession``'s (key, application); the account's data is
    read again from Telegram when it's checked."""
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        raise SessionImportError(f"это не .jsession: {e}") from None
    app = data.get("application") if isinstance(data, dict) else None
    if not isinstance(app, dict) or not data.get("auth_key") or not app.get("api_id") or not app.get("api_hash"):
        raise SessionImportError("это не .jsession: нет auth_key или application.api_id/api_hash")
    return data["auth_key"], app


# Run as `python -c` in a child process: argv[1] the tdata folder, the passcode
# on stdin; prints {"key": StringSession} or {"error": code}.
_TDATA_READER = r"""
import asyncio, json, sys
try:
    from opentele.api import UseCurrentSession
    from opentele.exception import OpenTeleException, TDataBadDecryptKey
    from opentele.td import TDesktop
except ImportError:
    print(json.dumps({"error": "no_opentele"})); sys.exit()
from telethon.sessions import StringSession
passcode = sys.stdin.read()
try:
    tdesk = TDesktop(sys.argv[1], passcode=passcode or None)
except TDataBadDecryptKey:
    print(json.dumps({"error": "passcode"})); sys.exit()
except OpenTeleException as e:
    print(json.dumps({"error": "bad", "detail": str(e)[:200]})); sys.exit()
if not tdesk.isLoaded() or not tdesk.accountsCount:
    print(json.dumps({"error": "empty"})); sys.exit()
if tdesk.accountsCount > 1:
    print(json.dumps({"error": "many", "detail": str(tdesk.accountsCount)})); sys.exit()
client = asyncio.run(tdesk.ToTelethon(session=StringSession(), flag=UseCurrentSession))
print(json.dumps({"key": client.session.save()}))
"""

_TDATA_ERRORS = {
    "no_opentele": "на сервере не установлен opentele-ng (pip install -r requirements.txt)",
    "empty": "в папке tdata нет вошедшего аккаунта",
    "many": "в tdata несколько аккаунтов ({detail}) — у проекта одна сессия; выйдите из лишних в "
            "Telegram Desktop и запакуйте заново",
    "bad": "папка tdata не читается: {detail}",
}


async def read_tdata_key(tdata_dir: str, passcode: Optional[str] = None) -> str:
    """The tdata's account key as a StringSession (offline: nothing connects)."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-I", "-c", _TDATA_READER, tdata_dir,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate((passcode or "").encode()), TDATA_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise SessionImportError("папка tdata не прочиталась за отведённое время") from None
    lines = out.decode(errors="replace").strip().splitlines()
    try:
        result = json.loads(lines[-1])
    except (IndexError, ValueError):
        tail = err.decode(errors="replace").strip().splitlines()
        raise SessionImportError(f"папка tdata не читается: {tail[-1] if tail else 'нет ответа'}") from None
    if result.get("error") == "passcode":
        raise NeedPasscode("неверный код-пароль" if passcode else "tdata защищена код-паролем Telegram Desktop")
    if "error" in result:
        raise SessionImportError(_TDATA_ERRORS[result["error"]].format(detail=result.get("detail", "")))
    return result["key"]


def _key_bytes(key: str) -> Optional[bytes]:
    try:
        auth = StringSession(key).auth_key
    except Exception:  # noqa: BLE001 - a malformed string: no key to compare
        return None
    return auth.key if auth else None


def existing_with_key(key: str, sessions_dir: Path) -> Optional[Path]:
    """The .jsession already holding this key (read offline). Connecting it a
    second time while a mirror runs on it would risk AUTH_KEY_DUPLICATED."""
    mine = _key_bytes(key)
    for path in sorted(sessions_dir.glob("*.jsession")) if sessions_dir.is_dir() else []:
        try:
            if mine is not None and _key_bytes(load_jsession(str(path))["auth_key"]) == mine:
                return path
        except (OSError, ValueError, KeyError):
            continue
    return None


async def check_and_save(key: str, application: dict, sessions_dir: Path) -> Path:
    """Connect with ``key`` presenting ``application``; a signed-in account is
    saved as ``<sessions_dir>/<phone>.jsession`` (an older file of that number
    is kept as .bak by save_jsession)."""
    if (same := existing_with_key(key, sessions_dir)) is not None:
        raise SessionImportError(f"эта сессия уже загружена: {same.name}")
    client = build_telegram_client(
        key, application["api_id"], application["api_hash"],
        device_model=application.get("device_name"), system_version=application.get("sdk"),
        app_version=application.get("app_version"), lang_pack=application.get("lang_pack"),
        system_lang_code=application.get("system_lang_code"), connection_retries=2, retry_delay=1,
    )

    async def account():
        await client.connect()
        return await client.get_me() if await client.is_user_authorized() else None

    try:
        me = await asyncio.wait_for(account(), CONNECT_TIMEOUT)
    except asyncio.TimeoutError:
        raise SessionImportError(f"Telegram не ответил за {CONNECT_TIMEOUT} с") from None
    except Exception as e:  # noqa: BLE001 - AuthKeyUnregistered, a dead DC…: shown to the admin
        raise SessionImportError(f"сессия не подключилась: {type(e).__name__}: {e}") from None
    finally:
        await client.disconnect()
    if me is None:
        raise SessionImportError("сессия не авторизована (из аккаунта вышли или ключ отозван)")
    path = sessions_dir / f"{me.phone or me.id}.jsession"
    save_jsession(str(path), client.session.save(), me, application)
    return path


async def import_folder(root: str, sessions_dir: Path, passcode: Optional[str] = None) -> Path:
    """The one account found under ``root`` (ZIPs already unpacked): a tdata
    folder or a .session (+ .json) — checked and saved; its new .jsession."""
    tdatas, sessions = find_tdata(root), find_sessions(root)
    found = len(tdatas) + len(sessions)
    if found == 0:
        raise SessionImportError("не найдено ни папки tdata, ни файла .session")
    if found > 1:
        raise SessionImportError(f"найдено аккаунтов: {found} — у проекта одна сессия, загружайте по одному")
    if tdatas:
        return await check_and_save(await read_tdata_key(tdatas[0], passcode), dict(TDESKTOP_APP), sessions_dir)
    path, meta = sessions[0]
    return await check_and_save(read_session_key(path), application_of(meta), sessions_dir)


async def import_files(files: dict, sessions_dir: Path, passcode: Optional[str] = None) -> Path:
    """``files``: name → bytes as uploaded (.zip, .session, .json, or one .jsession)."""
    jsessions = [data for name, data in files.items() if name.lower().endswith(".jsession")]
    if jsessions:
        if len(files) > 1:
            raise SessionImportError("файл .jsession присылайте отдельно, по одному")
        return await check_and_save(*jsession_key(jsessions[0]), sessions_dir)
    with tempfile.TemporaryDirectory(prefix="session-import-") as tmp:
        for name, data in files.items():
            name = os.path.basename(name)
            if name.lower().endswith(".zip"):
                await asyncio.to_thread(unpack, data, os.path.join(tmp, name[:-4] or "archive"))
            else:
                Path(tmp, name).write_bytes(data)
        return await import_folder(tmp, sessions_dir, passcode)
