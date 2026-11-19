"""Data gathering shared by several screens (no UI text here)."""

import logging
from dataclasses import dataclass
from typing import Any, Optional

from bot import configedit, configstore
from bot.systemd import Systemd, SystemdError, UnitState
from telemirror.projects import Project, ProjectError, list_projects, load_chat_names, load_project

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


async def session_holders(sysd: Systemd, project: Project, besides: str = "") -> list:
    """(project, unit) running on this project's session — its own units and
    those of the projects sharing the session file — except ``besides``."""
    mine = project.session_path.resolve()
    out = []
    for other in list_projects():
        if other.session_path.resolve() == mine:
            out += [(other, unit) for unit in await running_units(sysd, other) if unit != besides]
    return out


@dataclass(frozen=True)
class ProjectInfo:
    project: Project
    missing: bool  # no config file
    snapshot: Optional[configstore.Snapshot]  # None: nothing to show / failed
    error: Optional[str]

    @property
    def readable(self) -> bool:
        return self.snapshot is not None

    @property
    def writable(self) -> bool:
        return self.snapshot is not None and not self.missing

    @property
    def directions(self) -> list:
        return configedit.directions(self.snapshot.data) if self.snapshot else []

    @property
    def data(self) -> Any:
        return self.snapshot.data if self.snapshot else {}

    @property
    def names(self) -> dict:
        """{chat id: title} (``projects/<key>/chats.json``)."""
        return load_chat_names(self.project.key)


def project_info(project: Project) -> ProjectInfo:
    if not project.config_path.exists():
        return ProjectInfo(project, True, None, None)
    try:
        return ProjectInfo(project, False, configstore.load(project), None)
    except Exception as e:  # noqa: BLE001 - a hand-broken YAML must not kill the screen
        return ProjectInfo(project, False, None, f"{type(e).__name__}: {e}")
