"""Accounts from other tools' files (telemirror/misc/session_import.py, the
panel's 📤 Загрузить сессию and `python -m telemirror.login --import`): a Telethon .session with
its seller's .json, a Telegram Desktop tdata — checked by connecting, saved as
a .jsession; one account per import."""

import importlib.util
import io
import json
import subprocess
import sys
import zipfile
from types import SimpleNamespace

import pytest
from telethon.crypto import AuthKey
from telethon.sessions import SQLiteSession, StringSession

from telemirror.misc import session_import as si
from telemirror.misc.jsession import TDESKTOP_APP, load_jsession
from tests.conftest import run

KEY = bytes(range(256))


def _session_file(path, key=KEY):
    """A Telethon .session (SQLite) holding ``key`` on DC 2."""
    session = SQLiteSession(str(path))
    session.set_dc(2, "149.154.167.51", 443)
    if key is not None:
        session.auth_key = AuthKey(key)
    session.save()
    session.close()


class FakeClient:
    instances: list = []
    AUTHORIZED = True
    FAIL = None  # an exception connect() raises

    def __init__(self, key, api_id, api_hash, **kwargs):
        self.key, self.api_id, self.kwargs = key, api_id, kwargs
        self.session = SimpleNamespace(save=lambda: key)
        self.authorized, self.fail, self.disconnected = self.AUTHORIZED, self.FAIL, False
        FakeClient.instances.append(self)

    async def connect(self):
        if self.fail:
            raise self.fail

    async def is_user_authorized(self):
        return self.authorized

    async def get_me(self):
        return SimpleNamespace(first_name="Импорт", last_name=None, id=5, phone="79990001122", username="imp")

    async def disconnect(self):
        self.disconnected = True


@pytest.fixture
def fake(monkeypatch):
    FakeClient.instances = []
    monkeypatch.setattr(si, "build_telegram_client", FakeClient)
    return FakeClient


def test_a_session_with_its_json_presents_the_sellers_app(tmp_path, fake):
    src, out = tmp_path / "src", tmp_path / "sessions"
    src.mkdir()
    _session_file(src / "79990001122.session")
    (src / "79990001122.json").write_text(json.dumps({
        "app_id": 4, "app_hash": "hash4", "device": "Pixel 7", "app_version": "11.0", "sdk": "Android 14",
        "lang_pack": "android", "system_lang_pack": "en-US", "twoFA": "not kept"}), encoding="utf-8")
    saved = run(si.import_folder(str(src), out))
    assert saved == out / "79990001122.jsession"
    data = load_jsession(str(saved))
    assert StringSession(data["auth_key"]).auth_key.key == KEY
    assert data["application"] == {"api_id": 4, "api_hash": "hash4", "device_name": "Pixel 7", "app_version": "11.0",
                                   "sdk": "Android 14", "lang_pack": "android", "system_lang_code": "en-US"}
    assert data["password"] is None  # the seller's 2FA isn't stored
    client = fake.instances[0]
    assert client.api_id == 4 and client.kwargs["device_model"] == "Pixel 7" and client.disconnected


def test_a_session_alone_presents_telegram_desktop(tmp_path, fake):
    _session_file(tmp_path / "a.session")
    saved = run(si.import_folder(str(tmp_path), tmp_path / "sessions"))
    assert load_jsession(str(saved))["application"] == TDESKTOP_APP


def test_refusals(tmp_path, fake, monkeypatch):
    out = tmp_path / "sessions"
    with pytest.raises(si.SessionImportError, match="не найдено"):
        run(si.import_folder(str(tmp_path), out))
    _session_file(tmp_path / "a.session")
    _session_file(tmp_path / "b.session")
    with pytest.raises(si.SessionImportError, match="найдено аккаунтов: 2"):
        run(si.import_folder(str(tmp_path), out))
    (tmp_path / "b.session").unlink()
    monkeypatch.setattr(FakeClient, "AUTHORIZED", False)
    with pytest.raises(si.SessionImportError, match="не авторизована"):
        run(si.import_folder(str(tmp_path), out))
    monkeypatch.setattr(FakeClient, "FAIL", ConnectionError("dc down"))
    with pytest.raises(si.SessionImportError, match="не подключилась: ConnectionError: dc down"):
        run(si.import_folder(str(tmp_path), out))
    assert all(c.disconnected for c in fake.instances)
    assert not out.exists()  # nothing saved


def test_a_bad_app_id_in_the_json_is_refused_plainly():
    with pytest.raises(si.SessionImportError, match="неверный app_id"):
        si.application_of({"app_id": "abc", "app_hash": "h"})


def test_a_session_without_a_key_is_refused(tmp_path):
    _session_file(tmp_path / "a.session", key=None)
    with pytest.raises(si.SessionImportError, match="нет ключа"):
        si.read_session_key(str(tmp_path / "a.session"))
    (tmp_path / "b.session").write_bytes(b"not sqlite at all")
    with pytest.raises(si.SessionImportError, match="не читается"):
        si.read_session_key(str(tmp_path / "b.session"))


def test_a_file_that_is_not_sqlite_is_refused_before_sqlite_opens_it(tmp_path, monkeypatch):
    """SQLiteSession on such a file fails with its sqlite3 connection left open
    (nothing to close it on): the header is checked first."""
    def no_sqlite(path):
        raise AssertionError("SQLiteSession opened a file that isn't SQLite")

    monkeypatch.setattr(si, "SQLiteSession", no_sqlite)
    (tmp_path / "b.session").write_bytes(b"not sqlite at all")
    with pytest.raises(si.SessionImportError, match="не читается: это не база SQLite"):
        si.read_session_key(str(tmp_path / "b.session"))


def test_a_key_already_saved_is_not_connected_again(tmp_path, fake):
    out = tmp_path / "sessions"
    _session_file(tmp_path / "a.session")
    run(si.import_folder(str(tmp_path), out))
    with pytest.raises(si.SessionImportError, match="уже загружена: 79990001122.jsession"):
        run(si.import_folder(str(tmp_path), out))
    assert len(fake.instances) == 1  # the second import never connected


def test_a_zip_of_a_session_and_its_json(tmp_path, fake):
    _session_file(tmp_path / "x.session")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.write(tmp_path / "x.session", "acc/x.session")
        archive.writestr("acc/x.json", json.dumps({"app_id": 9, "app_hash": "h9"}))
    saved = run(si.import_files({"acc.zip": buf.getvalue()}, tmp_path / "sessions"))
    assert load_jsession(str(saved))["application"]["api_id"] == 9
    with pytest.raises(si.SessionImportError, match="не ZIP"):
        run(si.import_files({"bad.zip": b"PK nope"}, tmp_path / "sessions"))


def test_the_cli_imports_a_session_file(tmp_path, fake, monkeypatch):
    from telemirror import login

    monkeypatch.setattr(login, "SESSIONS_DIR", tmp_path / "repo" / "sessions")
    monkeypatch.setattr(login, "REPO_DIR", tmp_path / "repo")
    _session_file(tmp_path / "a.session")
    (tmp_path / "a.json").write_text(json.dumps({"app_id": 4, "app_hash": "h"}), encoding="utf-8")
    assert login.import_account(tmp_path / "a.session") == "sessions/79990001122.jsession"
    assert fake.instances[0].api_id == 4  # its .json was read too


# ── a real tdata, built offline by opentele in a child process ──────────────

MAKE_TDATA = r"""
import asyncio, sys
from opentele.api import API, UseCurrentSession
from opentele.td import TDesktop
from opentele.tl import TelegramClient
from telethon.crypto import AuthKey
from telethon.sessions import StringSession

async def main(out, passcode):
    session = StringSession()
    session.set_dc(2, "149.154.167.51", 443)
    session.auth_key = AuthKey(bytes(range(256)))
    client = TelegramClient(session, api=API.TelegramDesktop)
    client.UserId = 777  # known: nothing connects
    tdesk = await TDesktop.FromTelethon(client, flag=UseCurrentSession)
    tdesk.SaveTData(out, passcode=passcode or None)

asyncio.run(main(sys.argv[1], sys.argv[2]))
"""

needs_opentele = pytest.mark.skipif(importlib.util.find_spec("opentele") is None, reason="opentele-ng not installed")


def _tdata(path, passcode=""):
    subprocess.run([sys.executable, "-I", "-c", MAKE_TDATA, str(path), passcode], check=True, capture_output=True)
    return path


@needs_opentele
def test_a_tdata_gives_its_key_without_loading_opentele_here(tmp_path):
    key = run(si.read_tdata_key(str(_tdata(tmp_path / "tdata"))))
    assert StringSession(key).auth_key.key == KEY and StringSession(key).dc_id == 2
    assert "opentele" not in sys.modules  # it patches Telethon: only ever in the child process


@needs_opentele
def test_a_tdata_with_a_passcode(tmp_path):
    tdata = str(_tdata(tmp_path / "tdata", "secret"))
    with pytest.raises(si.NeedPasscode, match="защищена код-паролем"):
        run(si.read_tdata_key(tdata))
    with pytest.raises(si.NeedPasscode, match="неверный код-пароль"):
        run(si.read_tdata_key(tdata, "wrong"))
    assert StringSession(run(si.read_tdata_key(tdata, "secret"))).auth_key.key == KEY


@needs_opentele
def test_a_zipped_tdata_is_imported_as_telegram_desktop(tmp_path, fake):
    _tdata(tmp_path / "Telegram" / "tdata")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for file in (tmp_path / "Telegram").rglob("*"):
            archive.write(file, file.relative_to(tmp_path))
    saved = run(si.import_files({"tdata.zip": buf.getvalue()}, tmp_path / "sessions"))
    data = load_jsession(str(saved))
    assert StringSession(data["auth_key"]).auth_key.key == KEY
    assert data["application"] == TDESKTOP_APP
