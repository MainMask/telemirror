"""telemirror.selfcheck: each check on faked systemd / HTTP / Postgres, the
config load in a real subprocess, and the panel's 🧾 Диагностика сервера."""

import json
import re
from pathlib import Path

import psycopg
import pytest

from bot import settings
from telemirror import projects, selfcheck
from telemirror.selfcheck import FAIL, OFF, OK, WARN, Check

REPO = Path(__file__).resolve().parent.parent


def _statuses(checks):
    return [c.status for c in checks]


@pytest.fixture
def dotenv(monkeypatch):
    """The .env keys the checks read: a dict the test fills."""
    values: dict = {}

    def fake(key, default=None, cast=None):
        value = values.get(key, default)
        return cast(value) if cast and key in values else value

    monkeypatch.setattr(selfcheck, "_env", fake)
    return values


# ── what it checks stays what deploy/ installs ──────────────────────────────


def test_units_are_the_ones_bootstrap_installs():
    script = (REPO / "deploy" / "bootstrap.sh").read_text(encoding="utf-8")
    loop = script.split("for unit in \\", 1)[1].split("; do", 1)[0]
    assert tuple(re.findall(r"telemirror[\w@.-]+", loop)) == selfcheck.UNITS
    assert all((REPO / "deploy" / "systemd" / u).is_file() for u in selfcheck.UNITS)


def test_timers_are_the_panels():
    assert selfcheck.TIMERS == settings.TIMERS
    assert set(selfcheck.TIMERS) <= set(selfcheck.UNITS) and selfcheck.PANEL_UNIT in selfcheck.UNITS


# ── .env and the bot ────────────────────────────────────────────────────────


def test_env_keys(dotenv):
    assert _statuses(selfcheck.check_env()) == [FAIL, FAIL]
    dotenv.update(PANEL_BOT_TOKEN="1:x", PANEL_ADMIN_IDS="12, 34")
    assert selfcheck.check_env() == []


def test_bot_token(dotenv, monkeypatch):
    assert selfcheck.check_bot() == []  # no token: check_env says it
    dotenv["PANEL_BOT_TOKEN"] = "1:secret"
    answers = iter([(200, json.dumps({"result": {"username": "panel_bot"}}).encode()), (401, b"")])
    monkeypatch.setattr(selfcheck, "_get", lambda url: next(answers))
    assert selfcheck.check_bot() == [Check(OK, "Бот панели @panel_bot", "отвечает")]
    assert "HTTP 401" in selfcheck.check_bot()[0].hint

    def refused(url):
        raise ConnectionRefusedError(url)

    monkeypatch.setattr(selfcheck, "_get", refused)
    (check,) = selfcheck.check_bot()
    assert check.status == FAIL and "secret" not in check.line()  # the token never shows


# ── the database ────────────────────────────────────────────────────────────


class FakeConn:
    def __init__(self, tables):
        self.tables = tables

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, args):
        row = (args[0] if args[0] in self.tables else None,)
        return type("Cursor", (), {"fetchone": lambda _self: row})()


def test_database(dotenv, monkeypatch):
    dotenv["USE_MEMORY_DB"] = True
    assert _statuses(selfcheck.check_database()) == [WARN]
    dotenv["USE_MEMORY_DB"] = False
    assert _statuses(selfcheck.check_database()) == [FAIL]  # neither DATABASE_URL nor DB_HOST

    dotenv.update(DB_HOST="db", DB_USER="u", DB_PASS="p@ss", DB_NAME="tm")
    seen = []

    def connect(dsn, **_):
        seen.append(dsn)
        return FakeConn(set(selfcheck.TABLES))

    monkeypatch.setattr(psycopg, "connect", connect)
    assert _statuses(selfcheck.check_database()) == [OK]
    assert seen == ["postgres://u:p%40ss@db/tm"]  # built the way the mirror builds it

    monkeypatch.setattr(psycopg, "connect", lambda dsn, **_: FakeConn({"binding_id"}))
    (check,) = selfcheck.check_database()
    assert check.status == WARN and "post_fingerprint" in check.hint and "binding_id" not in check.hint

    def down(dsn, **_):
        raise psycopg.OperationalError("connection refused\ndetails")

    monkeypatch.setattr(psycopg, "connect", down)
    (check,) = selfcheck.check_database()
    assert check.status == FAIL and check.hint.endswith("connection refused")


# ── systemd ─────────────────────────────────────────────────────────────────


def test_unit_files(tmp_path, monkeypatch):
    monkeypatch.setattr(selfcheck, "SYSTEMD_DIR", tmp_path)
    (check,) = selfcheck.check_units()
    assert check.status == FAIL and "bootstrap.sh" in check.hint
    for unit in selfcheck.UNITS:
        (tmp_path / unit).symlink_to(REPO / "deploy" / "systemd" / unit)
    assert selfcheck.check_units() == [Check(OK, "Юниты systemd", f"все {len(selfcheck.UNITS)} установлены")]
    (tmp_path / "telemirror-panel.service").unlink()
    (tmp_path / "telemirror-panel.service").write_text("[Unit]\n")  # a copy, not the repo's file
    (check,) = selfcheck.check_units()
    assert check.status == WARN and "telemirror-panel.service" in check.hint


def test_timers_and_panel(monkeypatch):
    states = {"telemirror-health.timer": "active", "telemirror-panel.service": "failed"}
    monkeypatch.setattr(selfcheck, "_show", lambda unit, *p: {"ActiveState": states.get(unit, "inactive")})
    assert _statuses(selfcheck.check_timers()) == [OK, OFF, OFF]  # off is the admin's choice, not ❌
    (check,) = selfcheck.check_panel()
    assert check.status == FAIL and "failed" in check.hint


# ── projects ────────────────────────────────────────────────────────────────


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path / "projects")
    session = tmp_path / "s.jsession"
    session.write_text(json.dumps({"auth_key": "k", "application": {"api_id": 1, "api_hash": "h"}}))
    return projects.Project("live", "Зеркало", "🪞", str(session), str(tmp_path / "c.yml"), 8123)


def test_live_mirror(project, monkeypatch):
    props = {"UnitFileState": "disabled", "ActiveState": "inactive"}
    monkeypatch.setattr(selfcheck, "_show", lambda unit, *p: props)
    answer = {"code": 204}

    def get(url):
        assert url == "http://127.0.0.1:8123/"
        if answer["code"] is None:
            raise ConnectionRefusedError()
        return answer["code"], b""

    monkeypatch.setattr(selfcheck, "_get", get)

    def live():
        return selfcheck._check_live(project, "🪞 Зеркало")

    assert live().status == OFF  # turned off in the panel
    props["UnitFileState"] = "enabled"
    assert live().status == FAIL and "journalctl -u telemirror@live.service" in live().hint
    (projects.PROJECTS_DIR).mkdir()
    (projects.PROJECTS_DIR / ".resume.json").write_text(json.dumps(
        [{"after": "telemirror-past@crs.service", "resume": ["telemirror@live.service"]}]))
    assert live() == Check(OFF, "🪞 Зеркало: зеркало", "на паузе, пока работает telemirror-past@crs.service")
    props["ActiveState"] = "active"
    assert live() == Check(OK, "🪞 Зеркало: зеркало", "работает")
    answer["code"] = None
    assert live().status == FAIL and "порт 8123 не отвечает" in live().hint
    answer["code"] = 404
    assert live().status == FAIL and "HTTP 404" in live().hint


def test_project_session_and_config(project, monkeypatch):
    monkeypatch.setattr(selfcheck, "_load_config", lambda p: "")
    assert _statuses(selfcheck.check_project(project, systemd=False)) == [OK, OK]
    Path(project.session).write_text("{}")
    monkeypatch.setattr(selfcheck, "_load_config", lambda p: "ValueError: bad mode")
    session, config = selfcheck.check_project(project, systemd=False)
    assert session.status == FAIL and "👤 Аккаунт" in session.hint
    assert config == Check(FAIL, "🪞 Зеркало: настройки", "ValueError: bad mode")


def test_broken_project_file_is_reported(project):
    (projects.PROJECTS_DIR / "bad").mkdir(parents=True)
    (projects.PROJECTS_DIR / "bad" / "project.yml").write_text("name: x\n")  # no session, no port
    (check,) = selfcheck.check_broken_projects()
    assert check.status == FAIL and check.what == "Проект bad"


def test_config_loads_in_a_subprocess_as_the_mirror_does(tmp_path, monkeypatch):
    """The real ``import telemirror.config`` of the project (its key → its project.yml)."""
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path)
    monkeypatch.setenv("TELEMIRROR_PROJECTS_DIR", str(tmp_path))
    session = tmp_path / "s.jsession"
    session.write_text(json.dumps({"auth_key": "k", "application": {"api_id": 1, "api_hash": "h"}}))
    config = tmp_path / "c.yml"
    (tmp_path / "live").mkdir()
    (tmp_path / "live" / "project.yml").write_text(json.dumps(
        {"name": "Зеркало", "session": str(session), "config": str(config), "port": 8123}))
    project = projects.load_project("live")
    config.write_text("directions:\n  - from: [-1001234567890]\n    to: [-1009876543210]\n")
    assert selfcheck._load_config(project) == ""
    config.write_text("mode: sideways\ndirections:\n  - from: [-1001234567890]\n    to: [-1009876543210]\n")
    assert "sideways" in selfcheck._load_config(project)


# ── the whole run, the CLI ──────────────────────────────────────────────────


def test_run_without_systemd_skips_its_checks(dotenv, project, monkeypatch):
    monkeypatch.setattr(selfcheck.shutil, "which", lambda name: None)
    monkeypatch.setattr(selfcheck, "check_units", lambda: pytest.fail("no systemd: no unit checks"))
    monkeypatch.setattr(selfcheck, "check_database", list)
    checks = selfcheck.run()
    assert Check(WARN, "Проекты", "ни одного — 📁 Проекты → ➕ Новый проект") in checks
    assert any(c.what == "systemd" and c.status == WARN for c in checks)


def test_main_exit_code(monkeypatch, capsys):
    monkeypatch.setattr(selfcheck, "run", lambda: [Check(OK, "a"), Check(OFF, "b", "выключено")])
    with pytest.raises(SystemExit) as done:
        selfcheck.main()
    assert done.value.code == 0
    assert capsys.readouterr().out.endswith("✅ 1 · ⚠️ 0 · ❌ 0\n")
    monkeypatch.setattr(selfcheck, "run", lambda: [Check(FAIL, "a")])
    with pytest.raises(SystemExit) as done:
        selfcheck.main()
    assert done.value.code == 1
