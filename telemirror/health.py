"""Periodic health check for ``telemirror.service`` — run by
``telemirror-health.timer`` every ~10 min.

``OnFailure=`` only fires once the unit reaches ``failed`` state, which a *slow*
crash-loop (each run survives a few minutes) never does. This catches that: it
alerts when systemd's restart counter climbs fast, or the unit is stuck.

    python -m telemirror.health
"""

import json
import subprocess
import sys
from pathlib import Path

from telemirror import alert

_UNIT = "telemirror.service"
_STATE = Path("/run/telemirror-health.json")  # tmpfs — resets on boot, like NRestarts
_FLAP_THRESHOLD = 3  # restarts since last check that count as flapping


def _show(prop: str) -> str:
    out = subprocess.run(
        ["systemctl", "show", _UNIT, "-p", prop, "--value"],
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
        print(f"telemirror.health: failed to write state: {e}", file=sys.stderr)


def check() -> list[str]:
    try:
        nrestarts = int(_show("NRestarts") or 0)
    except ValueError:
        nrestarts = 0
    active = _show("ActiveState")

    prev = _load_state()
    problems = []

    delta = nrestarts - prev.get("nrestarts", nrestarts)
    if delta >= _FLAP_THRESHOLD:
        problems.append(
            f"⚠️ {_UNIT}: {delta} restart(s) in this interval (total {nrestarts}) — flapping"
        )
    if active == "failed":
        problems.append(f"⚠️ {_UNIT}: ActiveState=failed")
    # Two consecutive checks stuck outside 'active'/'inactive' = not just a
    # transient restart. 'inactive' is excluded: Restart=always means a crashing
    # unit cycles through activating/failed and essentially never settles into
    # inactive on its own — a stable 'inactive' means systemd stopped it on
    # purpose (the telemirror-past-courses.service Conflicts= switch-over, or an
    # operator's manual stop), not a stuck unit.
    _settled = (None, "active", "inactive")
    if active not in _settled and prev.get("active") not in _settled:
        problems.append(f"⚠️ {_UNIT}: not active twice in a row (currently {active})")

    _save_state({"nrestarts": nrestarts, "active": active})
    return problems


def main() -> None:
    problems = check()
    if problems:
        alert.send_alert("\n".join(problems) + "\n\n" + alert.journal_tail(_UNIT)[-2500:])
    sys.exit(0)


if __name__ == "__main__":
    main()
