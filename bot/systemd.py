"""Async ``systemctl`` / ``journalctl`` access for the panel.

Only the units of existing projects (``telemirror@<key>``, ``telemirror-past@<key>``,
``telemirror-task@<key>``) and ``settings.TIMERS`` ever reach argv — no user
input does. ``Runner`` is injectable so tests never call systemd.
"""

import asyncio
import shutil
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, Sequence

from bot import settings
from telemirror.projects import list_projects

Runner = Callable[[Sequence[str]], Awaitable[tuple[int, str]]]

_SHOW_PROPS = (
    "ActiveState",
    "SubState",
    "Result",
    "ActiveEnterTimestamp",
    "InactiveEnterTimestamp",
    "NRestarts",
    "MemoryCurrent",
    "InvocationID",
    "ExecMainCode",
    "ExecMainStatus",
)


class SystemdError(Exception):
    pass


async def _exec(argv: Sequence[str]) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), settings.SYSTEMCTL_TIMEOUT_SEC)
    except asyncio.TimeoutError:
        return 124, f"timeout after {settings.SYSTEMCTL_TIMEOUT_SEC}s"
    finally:
        if proc.returncode is None:  # timed out, or the panel is stopping
            proc.kill()
            await proc.wait()
    return proc.returncode or 0, out.decode("utf-8", errors="replace")


@dataclass(frozen=True)
class UnitState:
    active: str  # ActiveState: active / inactive / failed / activating / deactivating …
    sub: str
    result: str  # success / exit-code / signal / …
    since: Optional[int]  # unix ts of entering the current active/inactive state
    restarts: int
    memory: Optional[int]  # bytes
    invocation: str
    main_code: Optional[int] = None  # ExecMainCode: 1 exited, 2 killed by a signal, 0 never ran
    main_status: Optional[int] = None  # ExecMainStatus: its exit code, or the signal

    @property
    def running(self) -> bool:
        return self.active in ("active", "activating", "reloading")

    @property
    def completed(self) -> bool:
        """Its last run exited 0 on its own. Not the same as ``result ==
        "success"``: systemd counts a stop by SIGTERM (``systemctl stop``, a
        unit started over it via Conflicts=) as a clean end too."""
        return self.main_code == 1 and self.main_status == 0


def _ts(value: str) -> Optional[int]:
    # `--timestamp=unix` renders as "@1700000000"; empty/"n/a" when never entered.
    value = value.strip()
    if value.startswith("@"):
        try:
            return int(value[1:])
        except ValueError:
            return None
    return None


def _int(value: str) -> Optional[int]:
    try:
        return int(value)
    except ValueError:
        return None  # "[not set]" / empty


def parse_show(output: str) -> UnitState:
    """Parse ``systemctl show -p … --timestamp=unix`` ``Key=Value`` lines."""
    props: dict[str, str] = {}
    for line in output.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            props[key] = value
    active = props.get("ActiveState", "unknown") or "unknown"
    since_key = "InactiveEnterTimestamp" if active in ("inactive", "failed") else "ActiveEnterTimestamp"
    return UnitState(
        active=active,
        sub=props.get("SubState", ""),
        result=props.get("Result", ""),
        since=_ts(props.get(since_key, "")),
        restarts=_int(props.get("NRestarts", "")) or 0,
        memory=_int(props.get("MemoryCurrent", "")),
        invocation=props.get("InvocationID", ""),
        main_code=_int(props.get("ExecMainCode", "")),
        main_status=_int(props.get("ExecMainStatus", "")),
    )


def _check(unit: str) -> str:
    if unit not in settings.TIMERS and not any(unit in p.units for p in list_projects()):
        raise ValueError(f"unit {unit!r} is not managed by the panel")
    return unit


class Systemd:
    def __init__(self, runner: Optional[Runner] = None) -> None:
        self._run: Runner = runner or _exec
        self.available = runner is not None or shutil.which("systemctl") is not None

    async def show(self, unit: str) -> Optional[UnitState]:
        """None when systemd isn't there (e.g. a dev machine)."""
        if not self.available:
            return None
        argv = ["systemctl", "show", _check(unit), "--timestamp=unix"]
        for prop in _SHOW_PROPS:
            argv += ["-p", prop]
        rc, out = await self._run(argv)
        if rc != 0:
            raise SystemdError(out.strip() or f"systemctl show exited {rc}")
        return parse_show(out)

    async def _control(self, verb: str, unit: str, *extra: str) -> None:
        if not self.available:
            raise SystemdError("systemctl is not available")
        # --no-block: queue the job and return — a live mirror may take up
        # to TimeoutStartSec to report READY=1, the bot must not hang on it.
        rc, out = await self._run(["systemctl", "--no-block", verb, *extra, _check(unit)])
        if rc != 0:
            raise SystemdError(out.strip() or f"systemctl {verb} exited {rc}")

    async def start(self, unit: str) -> None:
        await self._control("start", unit)

    async def stop(self, unit: str) -> None:
        await self._control("stop", unit)

    async def enable(self, unit: str) -> None:
        """Start now and on every boot (a mirror the admin turned on)."""
        await self._control("enable", unit, "--now")

    async def disable(self, unit: str) -> None:
        """Stop now and not on boot (a mirror the admin turned off)."""
        await self._control("disable", unit, "--now")

    async def restart(self, unit: str) -> None:
        await self._control("restart", unit)

    async def journal(
        self, unit: str, lines: int, invocation: str = "", grep: str = ""
    ) -> str:
        """Last ``lines`` journal lines of ``unit`` (only its ``invocation`` run
        when given; only lines containing ``grep`` when given)."""
        if not self.available:
            return ""
        argv = ["journalctl", "-u", _check(unit), "-n", str(lines), "--no-pager", "-o", "cat"]
        if invocation:
            argv.append(f"_SYSTEMD_INVOCATION_ID={invocation}")
        if grep:
            argv += ["--grep", grep]
        rc, out = await self._run(argv)
        # journalctl exits 1 when --grep matched nothing — not an error here.
        if rc != 0 and not (grep and rc == 1):
            raise SystemdError(out.strip() or f"journalctl exited {rc}")
        return out.strip()
