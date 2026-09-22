import asyncio
import signal


def cancel_on_sigterm() -> None:
    """Cancel the calling coroutine's own task on SIGTERM.

    Python doesn't handle SIGTERM by default (the process is killed
    outright, skipping every try/finally), which under systemd fires on
    every `systemctl stop`/`restart` and on watchdog timeout — not just
    crashes. Cancelling the task instead lets its own
    `except asyncio.CancelledError`/`finally` run a graceful shutdown.
    Must be called from within the task that should be cancelled.
    """
    task = asyncio.current_task()
    assert task is not None  # always set: called from within a running task
    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, task.cancel)
