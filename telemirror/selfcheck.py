"""Self-check of an installation: is everything a VPS needs in place — ``.env``,
the panel's bot, the database and its tables, the systemd units and timers,
every project's session, config and live mirror. Only reads: nothing is
started, changed or sent.

The projects' sessions are never connected: a running mirror holds the same
one, and a second connection risks AUTH_KEY_DUPLICATED (the session dies).

Like ``telemirror.alert``, reads ``.env`` keys itself and never imports
``telemirror.config`` (that raises on a broken config — exactly what this
must report); a project's config is loaded in a subprocess instead.

    python -m telemirror.selfcheck      # exit 1 when something is ❌

The panel shows the same list (⚙️ Настройки → 🧾 Диагностика сервера).
"""

import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import psycopg
from decouple import AutoConfig

from telemirror import projects
from telemirror.misc.dsn import build_dsn
from telemirror.misc.jsession import load_jsession
from telemirror.notify import parse_admins
from telemirror.projects import REPO_DIR, Project, ProjectError

OK, WARN, FAIL, OFF = "✅", "⚠️", "❌", "⚪"

# What deploy/bootstrap.sh links into SYSTEMD_DIR (a test keeps them equal).
UNITS = (
    "telemirror@.service", "telemirror-past@.service", "telemirror-task@.service",
    "telemirror-alert@.service", "telemirror-restart.service", "telemirror-restart.timer",
    "telemirror-health.service", "telemirror-health.timer", "telemirror-report.service",
    "telemirror-report.timer", "telemirror-panel.service",
)
TIMERS = ("telemirror-health.timer", "telemirror-restart.timer", "telemirror-report.timer")
PANEL_UNIT = "telemirror-panel.service"
TABLES = ("binding_id", "past_mode_checkpoint", "past_mode_drip", "broadcast_sync", "post_fingerprint")
SYSTEMD_DIR = Path("/etc/systemd/system")
TIMEOUT_SEC = 10
CONFIG_TIMEOUT_SEC = 120  # `import telemirror.config` loads cv2

_env = AutoConfig(search_path=str(REPO_DIR))


@dataclass(frozen=True)
class Check:
    status: str  # OK / WARN / FAIL / OFF
    what: str
    hint: str = ""

    def line(self) -> str:
        return f"{self.status} {self.what}" + (f" — {self.hint}" if self.hint else "")


def _show(unit: str, *props: str) -> Dict[str, str]:
    out = subprocess.run(
        ["systemctl", "show", unit, *(f"-p{p}" for p in props)],
        capture_output=True, text=True, timeout=TIMEOUT_SEC, check=False,
    ).stdout
    return dict(line.partition("=")[::2] for line in out.splitlines() if "=" in line)


def _get(url: str) -> tuple:
    """(HTTP status, body); no answer (refused, timed out) raises OSError."""
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SEC) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as e:
        return e.code, b""


def _load_config(project: Project) -> str:
    """The error's last line when the project's mirror couldn't load its
    config (the way ``telemirror@<key>.service`` does), else ""."""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", "import telemirror.config"], cwd=REPO_DIR,
            env={**os.environ, "TELEMIRROR_PROJECT": project.key},
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
            timeout=CONFIG_TIMEOUT_SEC, check=False,
        )
    except subprocess.TimeoutExpired:
        return f"не загрузились за {CONFIG_TIMEOUT_SEC} с"
    if proc.returncode == 0:
        return ""
    lines = proc.stderr.strip().splitlines()
    return lines[-1] if lines else f"код выхода {proc.returncode}"


# ── the checks ──────────────────────────────────────────────────────────────


def check_env() -> List[Check]:
    out = []
    if not _env("PANEL_BOT_TOKEN", default=""):
        out.append(Check(FAIL, "PANEL_BOT_TOKEN", "не задан в .env: панели и уведомлений не будет"))
    if not parse_admins(_env("PANEL_ADMIN_IDS", default="")):
        out.append(Check(FAIL, "PANEL_ADMIN_IDS", "не задан в .env: уведомления некому отправлять"))
    return out


def check_bot() -> List[Check]:
    token = _env("PANEL_BOT_TOKEN", default="")
    if not token:
        return []  # check_env has said it
    try:
        code, body = _get(f"https://api.telegram.org/bot{token}/getMe")
    except OSError as e:  # the URL (the token) isn't in the message: only its type
        return [Check(FAIL, "Бот панели", f"нет связи с api.telegram.org ({type(e).__name__})")]
    if code != 200:
        return [Check(FAIL, "Бот панели", f"Telegram не принял PANEL_BOT_TOKEN (HTTP {code})")]
    return [Check(OK, f"Бот панели @{json.loads(body)['result']['username']}", "отвечает")]


def check_database() -> List[Check]:
    if _env("USE_MEMORY_DB", default=False, cast=bool):
        return [Check(WARN, "База", "USE_MEMORY_DB: после перезапуска зеркало не помнит скопированное — "
                                    "правки и удаления не дойдут, повтор поста может дать дубль")]
    url = _env("DATABASE_URL", default=None)
    host = _env("DB_HOST", default=None)
    if not url and not host:
        return [Check(FAIL, "База", "в .env нет ни DATABASE_URL, ни DB_HOST")]
    dsn = url or build_dsn(_env("DB_USER", default=None), _env("DB_PASS", default=None), host,
                           _env("DB_NAME", default=None))
    try:
        with psycopg.connect(dsn, connect_timeout=TIMEOUT_SEC, autocommit=True) as conn:
            missing = [t for t in TABLES if conn.execute("SELECT to_regclass(%s)", (t,)).fetchone() in (None, (None,))]
    except psycopg.Error as e:
        first = str(e).strip().splitlines()
        return [Check(FAIL, "База", f"не подключиться: {first[0] if first else type(e).__name__}")]
    if missing:
        return [Check(WARN, "База", f"нет таблиц {', '.join(missing)} — их создаёт зеркало при запуске: "
                                    "запустите или перезапустите зеркала")]
    return [Check(OK, "База", "подключение есть, таблицы на месте")]


def check_units() -> List[Check]:
    missing, foreign = [], []
    for unit in UNITS:
        link = SYSTEMD_DIR / unit
        if not link.exists():
            missing.append(unit)
        elif link.resolve() != (REPO_DIR / "deploy" / "systemd" / unit).resolve():
            foreign.append(unit)
    out = []
    if missing:
        out.append(Check(FAIL, "Юниты systemd", f"не установлены: {', '.join(missing)} — "
                                                "выполните sudo deploy/bootstrap.sh"))
    if foreign:
        out.append(Check(WARN, "Юниты systemd", f"установлены не из {REPO_DIR}: {', '.join(foreign)} — "
                                                "выполните sudo deploy/bootstrap.sh"))
    return out or [Check(OK, "Юниты systemd", f"все {len(UNITS)} установлены")]


def check_timers() -> List[Check]:
    out = []
    for timer in TIMERS:
        if _show(timer, "ActiveState").get("ActiveState") == "active":
            out.append(Check(OK, timer, "включён"))
        else:
            out.append(Check(OFF, timer, "выключен (включается в ⚙️ Настройки)"))
    return out


def check_panel() -> List[Check]:
    state = _show(PANEL_UNIT, "ActiveState").get("ActiveState", "")
    if state == "active":
        return [Check(OK, PANEL_UNIT, "работает")]
    return [Check(FAIL, PANEL_UNIT, f"не работает ({state or 'нет данных'}) — "
                                    f"systemctl enable --now {PANEL_UNIT}")]


def check_broken_projects() -> List[Check]:
    """``list_projects`` skips a broken ``project.yml``: here it's said."""
    out = []
    for path in sorted(projects.PROJECTS_DIR.glob("*/project.yml")) if projects.PROJECTS_DIR.is_dir() else []:
        try:
            projects.load_project(path.parent.name)
        except ProjectError as e:
            out.append(Check(FAIL, f"Проект {path.parent.name}", str(e)))
    return out


def _paused(unit: str) -> str:
    """The unit ``unit`` waits for, when the panel paused it (a run on its
    session — ``bot/turns.py``'s ``projects/.resume.json``), else ""."""
    try:
        entries = json.loads((projects.PROJECTS_DIR / ".resume.json").read_text(encoding="utf-8"))
        return next((e["after"] for e in entries if unit in e.get("resume", ())), "")
    except (OSError, ValueError, TypeError, KeyError):
        return ""


def check_project(project: Project, systemd: bool) -> List[Check]:
    name = f"{project.icon} {project.name}"
    out = []
    try:
        load_jsession(str(project.session_path))
        out.append(Check(OK, f"{name}: аккаунт", "файл сессии на месте"))
    except (OSError, ValueError) as e:
        out.append(Check(FAIL, f"{name}: аккаунт", f"файл сессии {project.session} не читается "
                                                   f"({type(e).__name__}) — ⚙️ Настройки проекта → 👤 Аккаунт"))
    error = _load_config(project)
    out.append(Check(FAIL, f"{name}: настройки", error) if error else Check(OK, f"{name}: настройки", "читаются"))
    if systemd:
        out.append(_check_live(project, name))
    return out


def _check_live(project: Project, name: str) -> Check:
    what = f"{name}: зеркало"
    props = _show(project.live_unit, "UnitFileState", "ActiveState")
    active = props.get("ActiveState", "")
    if props.get("UnitFileState") != "enabled":
        return Check(OFF, what, "выключено")
    if active != "active":
        after = _paused(project.live_unit)
        if after:
            return Check(OFF, what, f"на паузе, пока работает {after}")
        return Check(FAIL, what, f"включено, но не работает ({active or 'нет данных'}) — "
                                 f"journalctl -u {project.live_unit}")
    host = _env("HOST", default="0.0.0.0")
    host = "127.0.0.1" if host in ("", "0.0.0.0", "::") else host
    try:
        code, _ = _get(f"http://{host}:{project.port}/")
    except OSError as e:
        return Check(FAIL, what, f"работает, но порт {project.port} не отвечает ({type(e).__name__})")
    if code != 204:
        return Check(FAIL, what, f"на порту {project.port} отвечает не зеркало (HTTP {code})")
    return Check(OK, what, "работает")


def run() -> List[Check]:
    checks = [*check_env(), *check_bot(), *check_database()]
    systemd = shutil.which("systemctl") is not None
    if systemd:
        checks += [*check_units(), *check_timers(), *check_panel()]
    else:
        checks.append(Check(WARN, "systemd", "нет на этой машине — юниты, таймеры и зеркала не проверялись"))
    checks += check_broken_projects()
    found = projects.list_projects()
    if not found:
        checks.append(Check(WARN, "Проекты", "ни одного — 📁 Проекты → ➕ Новый проект"))
    for project in found:
        checks += check_project(project, systemd)
    return checks


def summary(checks: List[Check]) -> str:
    """``✅ 9 · ⚠️ 1 · ❌ 0`` (⚪ — switched off on purpose — isn't counted)."""
    return " · ".join(f"{s} {sum(c.status == s for c in checks)}" for s in (OK, WARN, FAIL))


def main() -> None:
    checks = run()
    print("\n".join(c.line() for c in checks))
    print(f"\n{summary(checks)}")
    sys.exit(1 if any(c.status == FAIL for c in checks) else 0)


if __name__ == "__main__":
    main()
