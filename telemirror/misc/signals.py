import asyncio
import signal
import sys


def cancel_on_sigterm() -> None:
    """Cancel the calling coroutine's own task on SIGTERM.

    Python doesn't handle SIGTERM by default (the process is killed
    outright, skipping every try/finally), which under systemd fires on
    every `systemctl stop`/`restart` and on watchdog timeout — not just
    crashes. Cancelling the task instead lets its own
    `except asyncio.CancelledError`/`finally` run a graceful shutdown.
    Must be called from within the task that should be cancelled.

    A no-op on Windows: `loop.add_signal_handler` isn't supported there
    (raises `NotImplementedError`), and production only runs under systemd,
    which is Linux-only — so graceful-shutdown-on-SIGTERM isn't load-bearing
    on Windows, but crashing at startup there is a real regression (main.py
    otherwise supports Windows, see its `sys.platform == "win32"` branch).
    """
    if sys.platform == "win32":
        return
    task = asyncio.current_task()
    assert task is not None  # always set: called from within a running task
    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, task.cancel)
