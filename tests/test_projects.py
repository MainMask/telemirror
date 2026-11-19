"""telemirror.projects: projects = independent mirrors (projects/<key>/project.yml);
telemirror.config's TELEMIRROR_PROJECT picks one's session, mirror config and port."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from telemirror import projects
from telemirror.misc.jsession import TDESKTOP_APP, save_jsession

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def pdir(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(projects, "REPO_DIR", tmp_path)
    return tmp_path


def test_create_writes_project_and_empty_config(pdir):
    p = projects.create_project("Новости", "📰", "sessions/a.jsession")
    assert p.key == "novosti"
    assert p.port == projects.FIRST_PORT
    assert p.config == "projects/novosti/mirror.config.yml"
    assert yaml.safe_load(p.config_path.read_text())["directions"] == []
    assert projects.load_project("novosti") == p
    assert (p.live_unit, p.past_unit, p.task_unit) == (
        "telemirror@novosti.service",
        "telemirror-past@novosti.service",
        "telemirror-task@novosti.service",
    )


def test_keys_and_ports_are_unique(pdir):
    a = projects.create_project("Новости", "📰", "s.jsession")
    b = projects.create_project("новости!", "📰", "s.jsession")
    assert (a.key, b.key) == ("novosti", "novosti-2")
    assert b.port == a.port + 1


def test_key_fallback_and_length(pdir):
    assert projects.make_key("🔥🔥", set()) == "project"
    assert len(projects.make_key("очень длинное название проекта", set())) <= projects.KEY_MAX


def test_list_is_sorted_by_name(pdir):
    projects.create_project("Бета", "🅱️", "s.jsession")
    projects.create_project("альфа", "🅰️", "s.jsession")
    assert [p.name for p in projects.list_projects()] == ["альфа", "Бета"]


def test_update_and_delete(pdir):
    p = projects.create_project("Тест", "🧪", "s.jsession")
    assert projects.update_project(p.key, name="Прод", icon="🚀").name == "Прод"
    assert projects.load_project(p.key).icon == "🚀"
    archive = projects.delete_project(p.key)
    assert projects.list_projects() == []
    assert (archive / "project.yml").exists() and (archive / "mirror.config.yml").exists()
    assert archive.parent == projects.PROJECTS_DIR / ".deleted"


def test_delete_keeps_a_config_outside_the_project_dir(pdir):
    shared = pdir / ".configs" / "mirror.config.yml"
    shared.parent.mkdir()
    shared.write_text("directions: []\n")
    p = projects.create_project("Live", "🪞", "s.jsession", config=".configs/mirror.config.yml")
    projects.delete_project(p.key)
    assert shared.exists()


def test_sharing_session(pdir):
    a = projects.create_project("A", "🅰️", "sessions/one.jsession")
    b = projects.create_project("B", "🅱️", "sessions/one.jsession")
    projects.create_project("C", "©️", "sessions/two.jsession")
    assert [p.key for p in projects.sharing_session(a)] == [b.key]


def test_a_broken_project_file_is_skipped_in_the_list(pdir):
    projects.create_project("Живой", "🟢", "s.jsession")
    broken = pdir / "projects" / "bad" / "project.yml"
    broken.parent.mkdir(parents=True)
    broken.write_text("name: x\n")
    assert [p.name for p in projects.list_projects()] == ["Живой"]


def test_load_reports_missing_and_broken_files(pdir):
    with pytest.raises(projects.ProjectError, match="not found"):
        projects.load_project("nope")
    broken = pdir / "projects" / "bad" / "project.yml"
    broken.parent.mkdir(parents=True)
    broken.write_text("name: x\n")
    with pytest.raises(projects.ProjectError, match="invalid"):
        projects.load_project("bad")


def test_migrate_creates_live_and_courses_once(pdir, monkeypatch):
    (pdir / ".configs").mkdir()
    (pdir / ".configs" / "mirror.config.yml").write_text("directions: []\n")
    (pdir / ".configs" / "citadel_courses.config.yml").write_text("directions: []\n")
    (pdir / ".env").write_text("SESSION_FILE=sessions/7999.jsession\nPORT=8000\n")
    monkeypatch.delenv("SESSION_FILE", raising=False)
    monkeypatch.delenv("PORT", raising=False)

    assert len(projects.migrate()) == 2
    live, crs = projects.load_project("live"), projects.load_project("crs")
    assert (live.config, live.session, live.port) == (
        ".configs/mirror.config.yml", "sessions/7999.jsession", 8000,
    )
    assert (crs.config, crs.session, crs.port) == (
        ".configs/citadel_courses.config.yml", "sessions/7999.jsession", 8001,
    )
    assert projects.migrate() == []


def test_migrate_turns_a_session_string_into_a_jsession(pdir, monkeypatch):
    (pdir / ".configs").mkdir()
    (pdir / ".configs" / "mirror.config.yml").write_text("directions: []\n")
    (pdir / ".env").write_text("API_ID=12345\nAPI_HASH=hash\nSESSION_STRING=1AAAA\n")
    for key in ("SESSION_FILE", "API_ID", "API_HASH", "SESSION_STRING", "PORT"):
        monkeypatch.delenv(key, raising=False)

    projects.migrate()
    data = json.loads((pdir / "sessions" / "live.jsession").read_text())
    assert data["auth_key"] == "1AAAA"
    assert data["application"]["api_id"] == 12345
    assert projects.load_project("live").session == "sessions/live.jsession"


def test_config_runs_as_a_project(tmp_path):
    """telemirror.config with TELEMIRROR_PROJECT: session, mirror config and port all
    come from the project — not from SESSION_FILE / .configs / PORT."""
    pdir = tmp_path / "projects"
    session = tmp_path / "s.jsession"
    me = type("Me", (), {"first_name": "T", "last_name": None, "id": 1, "phone": "7", "username": None})
    save_jsession(str(session), "1PROJ", me, TDESKTOP_APP)
    (pdir / "demo").mkdir(parents=True)
    (pdir / "demo" / "mirror.config.yml").write_text(
        "directions:\n  - from: [-1001]\n    to: [-1002]\n"
    )
    (pdir / "demo" / "project.yml").write_text(yaml.safe_dump({
        "name": "Демо", "icon": "🧪", "session": str(session),
        "config": str(pdir / "demo" / "mirror.config.yml"), "port": 8123,
    }, allow_unicode=True))
    env = {k: v for k, v in os.environ.items()
           if k not in ("API_ID", "API_HASH", "SESSION_STRING", "SESSION_FILE", "PORT")}
    env.update(TELEMIRROR_PROJECT="demo", TELEMIRROR_PROJECTS_DIR=str(pdir), USE_MEMORY_DB="true")
    out = subprocess.run(
        [sys.executable, "-c", (
            "import json; from telemirror import config as c; print(json.dumps([c.SESSION_STRING, "
            "c.API_ID, c.PORT, sorted(c.CHAT_MAPPING)]))"
        )],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, check=True,
    ).stdout
    assert json.loads(out.strip().splitlines()[-1]) == ["1PROJ", 2040, 8123, [-1001]]


def test_a_project_without_its_config_file_refuses_to_start(tmp_path):
    """No fallback to ./.configs/mirror.config.yml (another mirror's config)
    when the project's own config file is missing."""
    pdir = tmp_path / "projects"
    session = tmp_path / "s.jsession"
    me = type("Me", (), {"first_name": "T", "last_name": None, "id": 1, "phone": "7", "username": None})
    save_jsession(str(session), "1PROJ", me, TDESKTOP_APP)
    (pdir / "demo").mkdir(parents=True)
    (pdir / "demo" / "project.yml").write_text(yaml.safe_dump({
        "name": "Демо", "session": str(session), "config": str(pdir / "demo" / "gone.yml"), "port": 8123,
    }, allow_unicode=True))
    env = {k: v for k, v in os.environ.items() if k not in ("SESSION_FILE", "PORT")}
    env.update(TELEMIRROR_PROJECT="demo", TELEMIRROR_PROJECTS_DIR=str(pdir), USE_MEMORY_DB="true")
    out = subprocess.run([sys.executable, "-c", "import telemirror.config"], cwd=REPO_ROOT, env=env,
                         capture_output=True, text=True)
    assert out.returncode != 0
    assert "ProjectError" in out.stderr and "gone.yml not found" in out.stderr


def test_chat_names_merge_and_survive_a_broken_file(pdir):
    p = projects.create_project("Новости", "📰", "sessions/a.jsession")
    assert projects.load_chat_names(p.key) == {}
    projects.save_chat_names(p.key, {-1001: "Первый", -1002: ""})  # an empty title isn't kept
    projects.save_chat_names(p.key, {-1003: "Третий", -1001: "Первый (новое имя)"})
    assert projects.load_chat_names(p.key) == {-1001: "Первый (новое имя)", -1003: "Третий"}
    projects.chat_names_path(p.key).write_text("{broken", encoding="utf-8")
    assert projects.load_chat_names(p.key) == {}
    projects.save_chat_names("gone", {-1001: "x"})  # no such project: nothing written
    assert not (pdir / "projects" / "gone").exists()
