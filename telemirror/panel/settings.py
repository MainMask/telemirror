"""Panel configuration: env keys and module constants.

Like ``telemirror.alert``, this reads only the keys it needs straight from
``.env`` / the environment and never imports ``config`` — that module builds the
whole mirror mapping (and loads cv2) at import and raises on a partial env,
while the panel must stay up exactly when the mirror's config is broken.
"""

from dataclasses import dataclass
from pathlib import Path

from decouple import config as _env

REPO_DIR = Path(__file__).resolve().parents[2]
CONFIGS_DIR = REPO_DIR / ".configs"


def parse_admin_ids(raw: str) -> frozenset[int]:
    """``"123, 456"`` → ``{123, 456}``. Raises ValueError on a non-integer item."""
    ids = set()
    for item in raw.replace(";", ",").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            ids.add(int(item))
        except ValueError:
            raise ValueError(
                f"PANEL_ADMIN_IDS: expected comma-separated Telegram user ids, got {item!r}"
            ) from None
    return frozenset(ids)


BOT_TOKEN: str = _env("PANEL_BOT_TOKEN", default="")
ADMIN_IDS: frozenset[int] = parse_admin_ids(_env("PANEL_ADMIN_IDS", default=""))
LOG_LEVEL: str = _env("LOG_LEVEL", default="INFO").upper()
# The live mirror ignores .configs/mirror.config.yml when this is set (config.py
# source priority) — the panel then shows the live config read-only.
YAML_CONFIG_ENV_SET: bool = bool(_env("YAML_CONFIG_ENV", default=""))
TECH_CHANNEL_SET: bool = str(_env("TECH_CHANNEL", default="")).strip() not in ("", "0")

# ── systemd units (deploy/systemd) ───────────────────────────────────────────
LIVE_UNIT = "telemirror.service"
COURSES_UNIT = "telemirror-past-courses.service"
TASK_UNIT = "telemirror-task@{}.service"  # instance = skylon_set module name
HEALTH_TIMER = "telemirror-health.timer"
RESTART_TIMER = "telemirror-restart.timer"

# Short keys used in callback data → unit names. The panel never passes
# anything but these constants to systemctl.
UNITS: dict[str, str] = {
    "live": LIVE_UNIT,
    "crs": COURSES_UNIT,
    "rs": TASK_UNIT.format("restrict_saving"),
    "sp": TASK_UNIT.format("sync_pins"),
}
# Units that hold the shared SESSION_STRING instead of the live mirror; at most
# one of them may run at a time (each one Conflicts= with telemirror.service).
EXCLUSIVE_UNIT_KEYS = ("crs", "rs", "sp")
TIMERS = (HEALTH_TIMER, RESTART_TIMER)

# ── maintenance tasks (telemirror-task@.service) ────────────────────────────
# unit key → skylon_set module run by the task unit
TASK_MODULES: dict[str, str] = {"rs": "restrict_saving", "sp": "sync_pins"}
# Flags of skylon_set/sync_pins.py the panel can toggle (the rest stay CLI-only).
SYNC_PINS_FLAGS = ("--additive", "--allow-clear", "--include-broadcast", "--thorough")
# Read by telemirror-task@.service as EnvironmentFile=; created by systemd via
# RuntimeDirectory= of telemirror-panel.service.
TASK_ENV_DIR = Path("/run/telemirror-panel")


# ── projects = mirror configurations ────────────────────────────────────────
@dataclass(frozen=True)
class Project:
    key: str
    path: Path
    unit_key: str
    # How the service reads the file: "file" — config.py's ./.configs path
    # (telemirror.service); "env" — passed as YAML_CONFIG_ENV
    # (telemirror-past-courses.service).
    loader: str
    live: bool


PROJECTS: tuple[Project, ...] = (
    Project("live", CONFIGS_DIR / "mirror.config.yml", "live", "file", live=True),
    Project(
        "crs", CONFIGS_DIR / "citadel_courses.config.yml", "crs", "env", live=False
    ),
)

# ── UI limits ────────────────────────────────────────────────────────────────
PAGE_SIZE = 8  # directions per page
JOURNAL_LINES = 15  # journal lines on a unit card
JOURNAL_MAX_CHARS = 2500  # keep the card well under Telegram's 4096
RESTART_COOLDOWN_SEC = 120  # min gap between panel-initiated (re)starts of one unit
VALIDATE_TIMEOUT_SEC = 120  # `import config` of a candidate file
