"""In-memory panel state that outlives a single update (lost on a panel
restart — by design: nothing here must survive one)."""

import time
from dataclasses import dataclass, field
from typing import Optional

from telemirror.panel import settings


@dataclass(frozen=True)
class Launch:
    args: tuple[str, ...]
    dry: bool
    at: float  # unix time


@dataclass
class Runtime:
    last_start: dict[str, float] = field(default_factory=dict)  # unit key → monotonic
    launches: dict[str, Launch] = field(default_factory=dict)  # task key → last launch
    sp_flags: set[str] = field(default_factory=set)

    def cooldown_left(self, unit_key: str) -> int:
        last = self.last_start.get(unit_key)
        if last is None:
            return 0
        return max(0, int(settings.RESTART_COOLDOWN_SEC - (time.monotonic() - last)))

    def mark_started(self, unit_key: str) -> None:
        self.last_start[unit_key] = time.monotonic()

    def last_launch(self, task_key: str) -> Optional[Launch]:
        return self.launches.get(task_key)
