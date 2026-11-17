"""Projects — independent mirrors: one mirror config, one account session, one
set of systemd units (``telemirror@<key>``, ``telemirror-past@<key>``,
``telemirror-task@<key>``).

    projects/<key>/project.yml        name, icon, session, config, port
    projects/<key>/mirror.config.yml  a new project's config (default location)

Projects may share a session file; they then run in turn (one process per
session — see ``telemirror.misc.session_lock``).

    python -m telemirror.projects migrate   # one-time: projects for the old units
"""

import logging
import os
import re
import shutil
import sys
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from typing import List, Optional

import yaml

logger = logging.getLogger(__name__)

REPO_DIR = Path(__file__).resolve().parent.parent
PROJECTS_DIR = Path(os.environ.get("TELEMIRROR_PROJECTS_DIR") or REPO_DIR / "projects")
SESSIONS_DIR = REPO_DIR / "sessions"

KEY_MAX = 20
FIRST_PORT = 8000
NEW_CONFIG = (
    "# Mirror config of a project created in the control panel.\n"
    "mode: copy\n"
    "disable_edit: false\n"
    "disable_delete: false\n"
    "directions: []\n"
)

_TRANSLIT = dict(zip(
    "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
    "a b v g d e e zh z i y k l m n o p r s t u f h ts ch sh sch - y - e yu ya".split(),
    strict=True,
))


class ProjectError(ValueError):
    pass


@dataclass(frozen=True)
class Project:
    key: str
    name: str
    icon: str
    session: str  # .jsession path, relative to the repo root or absolute
    config: str  # mirror config path, relative to the repo root or absolute
    port: int  # health endpoint of the live mirror

    @property
    def session_path(self) -> Path:
        return REPO_DIR / self.session

    @property
    def config_path(self) -> Path:
        return REPO_DIR / self.config

    @property
    def live_unit(self) -> str:
        return f"telemirror@{self.key}.service"

    @property
    def past_unit(self) -> str:
        return f"telemirror-past@{self.key}.service"

    @property
    def task_unit(self) -> str:
        return f"telemirror-task@{self.key}.service"

    @property
    def units(self) -> tuple:
        return (self.live_unit, self.past_unit, self.task_unit)


def _file(key: str) -> Path:
    return PROJECTS_DIR / key / "project.yml"


def access_report_path(key: str) -> Path:
    """Written by ``skylon_set/check_access.py``, shown by the panel's 🛂 Доступ."""
    return PROJECTS_DIR / key / "access.json"


def load_project(key: str) -> Project:
    try:
        data = yaml.safe_load(_file(key).read_text(encoding="utf-8")) or {}
        return Project(
            key=key,
            name=str(data["name"]),
            icon=str(data.get("icon") or "📁"),
            session=str(data["session"]),
            config=str(data.get("config") or f"projects/{key}/mirror.config.yml"),
            port=int(data["port"]),
        )
    except FileNotFoundError:
        raise ProjectError(f"project {key!r}: {_file(key)} not found") from None
    except (KeyError, TypeError, ValueError, yaml.YAMLError) as e:
        raise ProjectError(f"project {key!r}: invalid {_file(key)} ({e})") from None


def list_projects() -> List[Project]:
    """All projects by name; a broken ``project.yml`` is skipped (logged) — one
    hand-broken file must not hide the others. Its mirror refuses to start on
    its own (config.py's ``load_project``), which systemd reports."""
    found = []
    for path in sorted(PROJECTS_DIR.glob("*/project.yml")) if PROJECTS_DIR.is_dir() else []:
        try:
            found.append(load_project(path.parent.name))
        except ProjectError as e:
            logger.warning("%s — skipped", e)
    return sorted(found, key=lambda p: p.name.casefold())


def _save(project: Project) -> None:
    data = asdict(project)
    del data["key"]
    path = _file(project.key)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    os.replace(tmp, path)


def make_key(name: str, taken) -> str:
    """Latin slug of ``name`` (systemd instance + directory name), unique."""
    slug = "".join(_TRANSLIT.get(c, c) for c in name.lower())
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")[:KEY_MAX].strip("-") or "project"
    key, n = slug, 2
    while key in taken:
        suffix = f"-{n}"
        key, n = slug[: KEY_MAX - len(suffix)] + suffix, n + 1
    return key


def create_project(name: str, icon: str, session: str, config: Optional[str] = None) -> Project:
    existing = list_projects()
    key = make_key(name, {p.key for p in existing})
    port = max([p.port for p in existing], default=FIRST_PORT - 1) + 1
    project = Project(
        key=key, name=name, icon=icon, session=session,
        config=config or f"projects/{key}/mirror.config.yml", port=port,
    )
    if not project.config_path.exists():
        project.config_path.parent.mkdir(parents=True, exist_ok=True)
        project.config_path.write_text(NEW_CONFIG, encoding="utf-8")
    _save(project)
    return project


def update_project(key: str, **fields) -> Project:
    project = replace(load_project(key), **fields)
    _save(project)
    return project


def delete_project(key: str) -> Path:
    """Move ``projects/<key>/`` (its project.yml and its own config) to
    ``projects/.deleted/<key>-<time>/`` — a mistaken deletion stays undoable by
    moving it back. A config kept elsewhere (the migrated ``.configs/*.yml``)
    and the session file stay where they are. Returns the archive."""
    archive = PROJECTS_DIR / ".deleted" / f"{key}-{time.strftime('%Y%m%d-%H%M%S')}"
    archive.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(PROJECTS_DIR / key), str(archive))
    return archive


def sharing_session(project: Project) -> List[Project]:
    """Other projects on the same session file — they can only run in turn."""
    mine = project.session_path.resolve()
    return [
        p for p in list_projects()
        if p.key != project.key and p.session_path.resolve() == mine
    ]


def migrate() -> List[str]:
    """Create ``live`` and ``crs`` for the pre-project units (telemirror.service,
    telemirror-past-courses.service) from ``.env``. Idempotent."""
    from decouple import AutoConfig

    from telemirror.misc.jsession import save_jsession

    env = AutoConfig(search_path=str(REPO_DIR))
    done = []
    session = env("SESSION_FILE", default=None)
    if not session:
        session = "sessions/live.jsession"
        if not (REPO_DIR / session).exists():
            app = {
                "api_id": int(env("API_ID")),
                "api_hash": env("API_HASH"),
                "device_name": env("API_DEVICE_MODEL", default=None),
                "app_version": env("API_APP_VERSION", default=None),
                "sdk": env("API_SYSTEM_VERSION", default=None),
            }
            me = SimpleNamespace(first_name=None, last_name=None, id=None, phone=None, username=None)
            save_jsession(str(REPO_DIR / session), env("SESSION_STRING"), me, app)
            done.append(f"{session} written from SESSION_STRING")
    seeds = (
        ("live", "Основной", "🪞", ".configs/mirror.config.yml", int(env("PORT", default=FIRST_PORT))),
        ("crs", "Курсы", "🎓", ".configs/citadel_courses.config.yml", None),
    )
    for key, name, icon, config, port in seeds:
        if _file(key).exists() or not (REPO_DIR / config).exists():
            continue
        if port is None:
            port = max([p.port for p in list_projects()], default=FIRST_PORT - 1) + 1
        _save(Project(key, name, icon, session, config, port))
        done.append(f"project {key}: {config}, session {session}, port {port}")
    return done


if __name__ == "__main__":
    if sys.argv[1:] != ["migrate"]:
        sys.exit("usage: python -m telemirror.projects migrate")
    for line in migrate() or ["nothing to do — projects already exist"]:
        print(line)
