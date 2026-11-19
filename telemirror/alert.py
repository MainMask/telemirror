"""Send a one-off notice through the control panel bot to its admins
(``PANEL_BOT_TOKEN`` → ``PANEL_ADMIN_IDS``, ``telemirror.notify``) — signed
with the failed unit's project and carrying the panel's 📊 Задача button.

The bot, not an account: with several projects there's no single session to
send from, and an account that was banned or logged out can't report it
itself.

Used by ``telemirror-alert@.service`` (OnFailure=) and by ``telemirror.health``.
Reads only what it needs: ``.env`` keys and the project's ``project.yml`` (never
``import telemirror.config`` — that builds the whole mapping and can raise on a
broken config, exactly when we most need the alert to go out).

    python -m telemirror.alert telemirror@live.service
"""

import logging
import re
import socket
import subprocess
import sys
from datetime import datetime, timezone
from typing import Optional

from decouple import config as _env

from telemirror.misc.log_setup import setup_stdout_logger
from telemirror.notify import BotNotifier

logger = logging.getLogger("telemirror.alert")

_PROJECT_UNIT = re.compile(r"^telemirror(?P<kind>-past|-task)?@(?P<key>[^.]+)\.service$")


def journal_tail(unit: str, lines: int = 15) -> str:
    try:
        out = subprocess.run(
            ["journalctl", "-u", unit, "-n", str(lines), "--no-pager", "-o", "cat"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if out.returncode != 0 and not out.stdout.strip():  # e.g. no access: not "empty"
            return f"(журнал недоступен: {out.stderr.strip()[:200] or f'код {out.returncode}'})"
        return out.stdout.strip() or "(журнал пуст)"
    except Exception as e:  # noqa: BLE001 - best effort
        return f"(журнал недоступен: {e})"


def _failed_state_message(unit: str) -> str:
    match = _PROJECT_UNIT.match(unit)
    if match and match["kind"] == "-task":  # one-shot: no restarts to give up on
        head = f"‼️ {unit}: инструмент закончил работу с ошибкой."
    else:
        head = f"🔴 {unit} остановилась после сбоев и сама больше не запустится."
    return f"{head}\n\nПоследние строки журнала:\n{journal_tail(unit)[-3000:]}"


def notifier_of(unit: str) -> Optional[BotNotifier]:
    """The bot's notifier, signed with ``unit``'s project (when it's one's);
    None when the panel's bot isn't set up."""
    match = _PROJECT_UNIT.match(unit)
    if not match:
        return BotNotifier.from_env()
    kind = {None: "live", "-past": "past", "-task": "task"}[match["kind"]]
    return BotNotifier.from_env(match["key"], kind)


def _stamp(text: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return f"{text}\n\nсервер: {socket.gethostname()}  •  {now}"


def send_alert(text: str, unit: str = "") -> Optional[bool]:
    """Best-effort: deliver ``text`` about ``unit`` to the panel's admins, never
    raise (an alert must not fail the caller — an OnFailure chain or the health
    timer). Returns None when the bot isn't set up (deliberately nothing to
    do), True if an admin got it, False on a real delivery failure — so the
    caller (a oneshot systemd unit) can surface an actual failed send without
    also flagging the unremarkable "alerting isn't configured" case."""
    try:
        notifier = notifier_of(unit)
        if notifier is None:
            logger.info("PANEL_BOT_TOKEN / PANEL_ADMIN_IDS not set — nobody to alert")
            return None
        return notifier.send_sync(_stamp(text))
    except Exception as e:  # noqa: BLE001
        logger.error("failed to send (%s: %s)", type(e).__name__, e)
        return False


def main() -> None:
    setup_stdout_logger("telemirror", _env("LOG_LEVEL", default="INFO").upper())
    if len(sys.argv) != 2:
        sys.exit("usage: python -m telemirror.alert <unit>")
    unit = sys.argv[1]
    sys.exit(1 if send_alert(_failed_state_message(unit), unit) is False else 0)


if __name__ == "__main__":
    main()
