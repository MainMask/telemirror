"""Periodic health check of every project's live mirror
(``telemirror@<key>.service``) — run by ``telemirror-health.timer`` every ~10 min.

``OnFailure=`` only fires once the unit reaches ``failed`` state, which a *slow*
crash-loop (each run survives a few minutes) never does. This catches that: it
alerts when systemd's restart counter climbs fast, or the unit is stuck.

    python -m telemirror.health
"""

import json
import logging
import subprocess
import sys
from pathlib import Path

from telemirror import alert
from telemirror.misc.log_setup import setup_stdout_logger
from telemirror.projects import list_projects

logger = logging.getLogger("telemirror.health")

_STATE = Path("/run/telemirror-health.json")  # tmpfs — resets on boot, like NRestarts
_FLAP_THRESHOLD = 3  # restarts since last check that count as flapping


def _units() -> list:
    return [p.live_unit for p in list_projects()]


def _show(unit: str, prop: str) -> str:
    out = subprocess.run(
        ["systemctl", "show", unit, "-p", prop, "--value"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    return out.stdout.strip()


def _load_state() -> dict:
    try:
        return json.loads(_STATE.read_text())
    except (OSError, ValueError):
        return {}


def _save_state(state: dict) -> None:
    try:
        _STATE.write_text(json.dumps(state))
    except OSError as e:
        logger.warning("failed to write state: %s", e)


def _check_unit(unit: str, prev: dict) -> tuple:
    try:
        nrestarts = int(_show(unit, "NRestarts") or 0)
    except ValueError:
        nrestarts = 0
    active = _show(unit, "ActiveState")
    problems = []

    delta = nrestarts - prev.get("nrestarts", nrestarts)
    if delta >= _FLAP_THRESHOLD:
        problems.append(
            f"⚠️ {unit}: падает по кругу — {delta} перезапуск(ов) за 10 минут (всего {nrestarts})"
        )
    # Two consecutive checks stuck outside 'active'/'inactive' = not just a
    # transient restart. 'inactive' is excluded: Restart=always means a crashing
    # unit cycles through activating/failed and essentially never settles into
    # inactive on its own — a stable 'inactive' means it was stopped on purpose
    # (a project that isn't running, a history replay's / task's Conflicts=
    # switch-over, a shared-session pause, an operator's manual stop), not a
    # stuck unit. 'failed' is OnFailure='s alert (telemirror.alert), not this.
    _settled = (None, "active", "inactive", "failed")
    if active not in _settled and prev.get("active") not in _settled:
        problems.append(f"⚠️ {unit}: не работает две проверки подряд (сейчас: {active})")
    return problems, {"nrestarts": nrestarts, "active": active}


def check() -> list[tuple]:
    """``[(unit, problems)]`` for the units with a problem."""
    prev = _load_state()
    state, found = {}, []
    for unit in _units():
        problems, state[unit] = _check_unit(unit, prev.get(unit, {}))
        if problems:
            found.append((unit, problems))
    _save_state(state)
    return found


def main() -> None:
    setup_stdout_logger("telemirror", "INFO")
    result = None
    for unit, problems in check():
        sent = alert.send_alert(
            "\n".join(problems) + "\n\n" + alert.journal_tail(unit)[-2500:], unit
        )
        result = False if sent is False or result is False else sent
    sys.exit(1 if result is False else 0)


if __name__ == "__main__":
    main()
