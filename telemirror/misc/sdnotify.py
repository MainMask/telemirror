"""Minimal ``sd_notify(3)`` client — no dependency on libsystemd or a package.

Used by the live mirror under ``Type=notify`` / ``WatchdogSec=`` to tell systemd
it is up (``READY=1``) and still alive (``WATCHDOG=1``). Outside systemd (no
``NOTIFY_SOCKET``) every call is a no-op, so tests and bare runs are unaffected.
"""

import asyncio
import logging
import os
import socket
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)


def notify(state: str) -> bool:
    """Send one newline-free notification (``READY=1``, ``WATCHDOG=1``,
    ``STOPPING=1``, …). Returns True if it was sent, False if there is no socket
    or the send failed — never raises."""
    addr = os.environ.get("NOTIFY_SOCKET")
    if not addr:
        return False
    # "@" marks a Linux abstract-namespace socket (leading NUL byte).
    if addr[0] == "@":
        addr = "\0" + addr[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.connect(addr)
            sock.sendall(state.encode("utf-8"))
        return True
    except OSError as e:
        logger.warning("sd_notify(%s) failed: %s", state, e)
        return False


def watchdog_interval() -> "float | None":
    """Seconds between ``WATCHDOG=1`` pings — half of systemd's ``WatchdogSec`` —
    or None when no watchdog is configured for this unit."""
    usec = os.environ.get("WATCHDOG_USEC")
    if not usec:
        return None
    try:
        return int(usec) / 2 / 1_000_000
    except ValueError:
        return None


async def watchdog_loop(probe: Callable[[], Awaitable[bool]]) -> None:
    """Every ``watchdog_interval()`` seconds call ``await probe()`` and forward
    ``WATCHDOG=1`` only when it returns True. A False result — or a probe that
    hangs — withholds the ping, so systemd's ``WatchdogSec`` eventually kills and
    restarts the unit. Returns immediately when no watchdog is configured. Meant
    to run as a background task, cancelled on shutdown."""
    interval = watchdog_interval()
    if interval is None:
        return
    while True:
        await asyncio.sleep(interval)
        ok = False
        try:
            ok = await probe()
        except Exception as e:  # noqa: BLE001 - a probe error means "not healthy"
            logger.warning("watchdog probe raised: %s", e)
        if ok:
            notify("WATCHDOG=1")
        else:
            logger.error("watchdog: probe unhealthy, withholding ping")
