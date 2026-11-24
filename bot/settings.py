"""Panel configuration: env keys and module constants.

Like ``telemirror.alert``, this reads only the keys it needs straight from
``.env`` / the environment and never imports ``telemirror.config`` — that builds the
whole mirror mapping (and loads cv2) at import and raises on a partial env,
while the panel must stay up exactly when the mirror's config is broken.
"""

from pathlib import Path
from zoneinfo import ZoneInfo

from decouple import config as _env


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


# The admins' clock: dates they type (⏪ 📅 С даты…) and every time the panel shows.
TIMEZONE = ZoneInfo("Europe/Moscow")

BOT_TOKEN: str = _env("PANEL_BOT_TOKEN", default="")
ADMIN_IDS: frozenset[int] = parse_admin_ids(_env("PANEL_ADMIN_IDS", default=""))
LOG_LEVEL: str = _env("LOG_LEVEL", default="INFO").upper()

# ── systemd (deploy/systemd) ─────────────────────────────────────────────────
# A project's units are telemirror.projects.Project.live_unit / past_unit /
# task_unit; the panel passes nothing else to systemctl but these timers.
HEALTH_TIMER = "telemirror-health.timer"
RESTART_TIMER = "telemirror-restart.timer"
REPORT_TIMER = "telemirror-report.timer"
TIMERS = (HEALTH_TIMER, RESTART_TIMER, REPORT_TIMER)

# ── maintenance tasks (telemirror-task@<project>.service) ───────────────────
# screen id → telemirror.tasks module run by the task unit
TASK_MODULES: dict[str, str] = {
    "rs": "restrict_saving", "sp": "sync_pins", "ag": "anonymize_groups", "cc": "clear_channels",
    "ca": "check_access",
}
# Flags of telemirror.tasks.sync_pins the panel can toggle (the rest stay CLI-only).
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
VALIDATE_TIMEOUT_SEC = 120  # `import telemirror.config` of a candidate file
FILTER_PAGE_SIZE = 10  # filter items per page
ACCESS_REPORT_ROWS = 15  # 🛂 Проверка доступа problems listed on the screen (the journal has them all)
PROJECT_NAME_MAX = 40
CONFIRM_TTL_SEC = 600  # an old confirmation's «Да» must not run days later
LOGIN_TIMEOUT_SEC = 30  # one Telegram request of the sign-in by phone
PENDING_TTL_SEC = 900  # a form's sign-in / uploaded files, when the admin stops answering
ALBUM_LATENCY_SEC = 0.7  # files sent together: the wait for the album's next item
SYSTEMCTL_TIMEOUT_SEC = 15
START_GRACE_SEC = 120  # a unit not seen running this long after its start: it's over (failed to start)

# ── upload limits ───────────────────────────────────────────────────────────
CONFIG_MAX_BYTES = 256 * 1024  # 💾 Файл настроек → 📤 Загрузить
UPLOAD_MAX_BYTES = 20 * 1024 * 1024  # 📤 Загрузить сессию: what the Bot API lets a bot download
JSESSION_MAX_BYTES = 64 * 1024

# ── defaults of the mirror's own config (shown when a key is unset) ──────────
REPLAY_DELAY_DEFAULT = 0.5  # telemirror.directions.PastModeConfig.send_delay
SYNC_PINS_DEFAULT_MAX_PINS = 100  # telemirror.tasks.sync_pins --max-pins

# ── notifications (polling systemd from the panel) ──────────────────────────
WATCH_INTERVAL_SEC = 30
# A crash-looping mirror notifies at most this often (the first crash at once).
NOTIFY_COOLDOWN_SEC = 600
