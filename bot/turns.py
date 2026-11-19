"""Projects on one session file run in turn: one process per session (two
would split the updates and risk AUTH_KEY_DUPLICATED — see
``telemirror.misc.session_lock``). Starting a unit stops whatever else holds
that session; the live mirrors stopped so are brought back once that unit is
over (the watcher calls ``due``). Kept in ``projects/.resume.json`` so a panel
restart doesn't strand a paused mirror."""

import json
import logging
import time

from bot import settings, status
from bot.runtime import Runtime
from bot.systemd import Systemd, SystemdError
from telemirror import projects
from telemirror.projects import Project

logger = logging.getLogger(__name__)


def _file():
    return projects.PROJECTS_DIR / ".resume.json"


def load() -> list:
    try:
        return json.loads(_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _save(entries: list) -> None:
    _file().parent.mkdir(parents=True, exist_ok=True)
    tmp = _file().with_suffix(".tmp")
    tmp.write_text(json.dumps(entries), encoding="utf-8")
    tmp.replace(_file())


async def start(sysd: Systemd, runtime: Runtime, project: Project, unit: str, restart: bool = False) -> list:
    """Start ``unit`` of ``project``: first stop every other unit on its session
    (returned as [(project, unit)]). For a replay / a task the live mirrors
    among them are paused and come back after it (``due``); a mirror replaces
    them for good (disabled: a mirror runs until it's turned off, and two
    enabled on one session would clash on every boot). ``restart``: a running
    mirror is restarted (its project may have moved to a busy session)."""
    holders = [(p, u) for p, u in await status.session_holders(sysd, project) if u != unit]
    mirror = unit == project.live_unit
    for p, u in holders:
        await (sysd.disable(u) if mirror and u == p.live_unit else sysd.stop(u))
    # The runs stopped here hand over the mirrors paused for them: resumed when
    # they stop, those would kill this unit (Conflicts=) or clash with it on the session.
    stopped = {u for _, u in holders} | {unit}
    loaded = load()
    taken = [u for e in loaded if e["after"] in stopped for u in e["resume"] if u != unit]
    entries = [e for e in loaded if e["after"] not in stopped]
    if mirror:
        for u in taken:  # this mirror replaces them for good, like the running ones
            try:
                await sysd.disable(u)
            except (SystemdError, ValueError) as e:  # ValueError: its project was deleted
                logger.warning("panel: turning off paused %s failed: %s", u, e)
        lives = []
    else:
        lives = list(dict.fromkeys([u for p, u in holders if u == p.live_unit] + taken))
    if lives:
        entries.append({"after": unit, "resume": lives, "at": time.time(), "seen": False})
    if entries != loaded:  # a pause dropped (this unit among it) or added
        _save(entries)
    # a mirror is turned on for good (boot included); a replay / a task runs once
    if restart:
        await sysd.restart(unit)
    elif mirror:
        await sysd.enable(unit)
    else:
        await sysd.start(unit)
    runtime.mark_started(unit)
    logger.info("panel: started %s (paused: %s)", unit, [u for _, u in holders] or "nothing")
    return holders


async def due(sysd: Systemd) -> list:
    """Bring back the mirrors paused for units that are over; returns the
    (finished unit, resumed units) pairs."""
    entries, keep, done = load(), [], []
    if not entries:
        return []
    known = {u for p in projects.list_projects() for u in p.units}
    for entry in entries:
        # A deleted project's unit is over: the deletion turned it off (and
        # systemctl isn't asked about units of no project).
        if entry["after"] in known:
            st = await status.unit_state(sysd, entry["after"])
            if st is None:
                keep.append(entry)  # systemctl failed this round
                continue
            if st.running:
                keep.append({**entry, "seen": True})
                continue
            if not entry["seen"] and time.time() - entry["at"] < settings.START_GRACE_SEC:
                keep.append(entry)  # its start is still queued
                continue
        resumed = []
        for unit in entry["resume"]:
            try:
                await sysd.start(unit)
                resumed.append(unit)
            except Exception as e:  # noqa: BLE001 - one bad unit must not block the others
                logger.warning("panel: resuming %s failed: %s", unit, e)
        done.append((entry["after"], resumed))
    if keep != entries:
        _save(keep)
    return done
