"""In-memory panel state that outlives a single update (lost on a panel
restart — by design: nothing here must survive one)."""

import time
from dataclasses import dataclass, field
from typing import Optional

from telemirror.panel import settings


@dataclass(frozen=True)
class Launch:
    args: tuple
    dry: bool
    at: float  # unix time
    config: str = ""  # sha of the project's config at the launch (maintenance.config_sha)


@dataclass
class Runtime:
    last_start: dict = field(default_factory=dict)  # unit → monotonic
    launches: dict = field(default_factory=dict)  # (project, task) → last Launch
    sp_flags: dict = field(default_factory=dict)  # project → set of sync_pins flags
    sp_opts: dict = field(default_factory=dict)  # project → {"max_pins": int, "only": tuple of donor ids}

    def cooldown_left(self, unit: str) -> int:
        last = self.last_start.get(unit)
        if last is None:
            return 0
        return max(0, int(settings.RESTART_COOLDOWN_SEC - (time.monotonic() - last)))

    def mark_started(self, unit: str) -> None:
        self.last_start[unit] = time.monotonic()

    def last_launch(self, project: str, task: str) -> Optional[Launch]:
        return self.launches.get((project, task))

    def flags(self, project: str) -> set:
        return self.sp_flags.setdefault(project, set())

    def opts(self, project: str) -> dict:
        return self.sp_opts.setdefault(project, {})
