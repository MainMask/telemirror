"""Panel configuration: env keys and module constants.

Like ``telemirror.alert``, this reads only the keys it needs straight from
``.env`` / the environment and never imports ``config`` — that module builds the
whole mirror mapping (and loads cv2) at import and raises on a partial env,
while the panel must stay up exactly when the mirror's config is broken.
"""

from pathlib import Path

from decouple import config as _env

REPO_DIR = Path(__file__).resolve().parents[2]


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

# ── systemd (deploy/systemd) ─────────────────────────────────────────────────
# A project's units are telemirror.projects.Project.live_unit / past_unit /
# task_unit; the panel passes nothing else to systemctl but these timers.
HEALTH_TIMER = "telemirror-health.timer"
RESTART_TIMER = "telemirror-restart.timer"
TIMERS = (HEALTH_TIMER, RESTART_TIMER)

# ── maintenance tasks (telemirror-task@<project>.service) ───────────────────
# screen id → skylon_set module run by the task unit
TASK_MODULES: dict[str, str] = {
    "rs": "restrict_saving", "sp": "sync_pins", "ag": "anonymize_groups", "cc": "clear_channels",
    "ca": "check_access",
}
# Flags of skylon_set/sync_pins.py the panel can toggle (the rest stay CLI-only).
SYNC_PINS_FLAGS = ("--additive", "--allow-clear", "--include-broadcast", "--thorough")
SYNC_PINS_MAX_PINS = (1, 1000)  # bounds of --max-pins from the panel (the script's default: 100)
# Read by telemirror-task@.service as EnvironmentFile=; created by systemd via
# RuntimeDirectory= of telemirror-panel.service.
TASK_ENV_DIR = Path("/run/telemirror-panel")

# ── UI limits ────────────────────────────────────────────────────────────────
PAGE_SIZE = 8  # directions / projects / accounts per page
JOURNAL_LINES = 15  # journal lines on a unit card
JOURNAL_MAX_CHARS = 2500  # keep the card well under Telegram's 4096
RESTART_COOLDOWN_SEC = 120  # min gap between panel-initiated (re)starts of one unit
VALIDATE_TIMEOUT_SEC = 120  # `import config` of a candidate file
FILTER_PAGE_SIZE = 10  # filter items per page
CONFIRM_TTL_SEC = 600  # an old confirmation's «Да» must not run days later
LOGIN_TIMEOUT_SEC = 30  # one Telegram request of the sign-in by phone

# ── notifications (polling systemd from the panel) ──────────────────────────
WATCH_INTERVAL_SEC = 30
# A crash-looping mirror notifies at most this often (the first crash at once).
NOTIFY_COOLDOWN_SEC = 600
