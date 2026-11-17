"""Data gathering shared by several screens (no UI text here)."""

import logging
from dataclasses import dataclass
from typing import Any, Optional

from telemirror.panel import configstore, settings
from telemirror.panel.settings import Project
from telemirror.panel.systemd import Systemd, SystemdError, UnitState

logger = logging.getLogger(__name__)


async def unit_state(sysd: Systemd, key: str) -> Optional[UnitState]:
    """None when systemd is unavailable or the query failed (logged)."""
    try:
        return await sysd.show(settings.UNITS[key])
    except SystemdError as e:
        logger.warning("panel: systemctl show %s failed: %s", settings.UNITS[key], e)
        return None


async def running_exclusive(sysd: Systemd) -> list[str]:
    """Keys of session-holding units (replay/maintenance) that are running."""
    out = []
    for key in settings.EXCLUSIVE_UNIT_KEYS:
        st = await unit_state(sysd, key)
        if st is not None and st.running:
            out.append(key)
    return out


def visible_projects() -> list[Project]:
    """The live project always (it may be env-configured); the others only
    when their file exists."""
    return [p for p in settings.PROJECTS if p.live or p.path.exists()]


def project_by_key(key: str) -> Optional[Project]:
    return next((p for p in visible_projects() if p.key == key), None)


@dataclass(frozen=True)
class ProjectInfo:
    project: Project
    read_only: Optional[str]  # configstore.read_only_reason
    snapshot: Optional[configstore.Snapshot]  # None: nothing to show / failed
    error: Optional[str]

    @property
    def readable(self) -> bool:
        return self.snapshot is not None

    @property
    def writable(self) -> bool:
        return self.snapshot is not None and self.read_only is None

    @property
    def directions(self) -> list:
        return configstore.directions(self.snapshot.data) if self.snapshot else []

    @property
    def data(self) -> Any:
        return self.snapshot.data if self.snapshot else {}


def project_info(project: Project) -> ProjectInfo:
    reason = configstore.read_only_reason(project)
    # With YAML_CONFIG_ENV the file isn't what the mirror runs — showing it
    # would mislead; in env mode / missing there is no file at all.
    if reason is not None:
        return ProjectInfo(project, reason, None, None)
    try:
        return ProjectInfo(project, None, configstore.load(project), None)
    except Exception as e:  # noqa: BLE001 - a hand-broken YAML must not kill the screen
        return ProjectInfo(project, None, None, f"{type(e).__name__}: {e}")


def total_directions(infos: list[ProjectInfo]) -> Optional[int]:
    counted = [len(i.directions) for i in infos if i.readable]
    return sum(counted) if counted else None
