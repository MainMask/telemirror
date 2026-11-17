"""Data gathering shared by several screens (no UI text here)."""

import logging
from dataclasses import dataclass
from typing import Any, Optional

from telemirror.panel import configstore
from telemirror.panel.systemd import Systemd, SystemdError, UnitState
from telemirror.projects import Project, ProjectError, list_projects, load_project

logger = logging.getLogger(__name__)


async def unit_state(sysd: Systemd, unit: str) -> Optional[UnitState]:
    """None when systemd is unavailable or the query failed (logged)."""
    try:
        return await sysd.show(unit)
    except (SystemdError, ValueError) as e:
        logger.warning("panel: systemctl show %s failed: %s", unit, e)
        return None


def find(key: str) -> Optional[Project]:
    try:
        return load_project(key)
    except ProjectError:
        return None


async def running_units(sysd: Systemd, project: Project) -> list:
    """The project's units that are running now."""
    out = []
    for unit in project.units:
        st = await unit_state(sysd, unit)
        if st is not None and st.running:
            out.append(unit)
    return out


async def session_holders(sysd: Systemd, project: Project) -> list:
    """(project, unit) running on this project's session — its own units and
    those of the projects sharing the session file."""
    mine = project.session_path.resolve()
    out = []
    for other in list_projects():
        if other.session_path.resolve() == mine:
            out += [(other, unit) for unit in await running_units(sysd, other)]
    return out


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
    def replaceable(self) -> bool:
        """The whole file may be swapped (rollback / upload) — even when it
        doesn't parse: that is exactly when those two are needed."""
        return self.read_only is None

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
    if reason is not None:
        return ProjectInfo(project, reason, None, None)
    try:
        return ProjectInfo(project, None, configstore.load(project), None)
    except Exception as e:  # noqa: BLE001 - a hand-broken YAML must not kill the screen
        return ProjectInfo(project, None, None, f"{type(e).__name__}: {e}")
