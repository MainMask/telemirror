"""One process per Telegram session: an exclusive advisory lock on
``<session>.lock``, held until the process exits. Two processes on one auth
key split the updates between them (each mirror loses messages) and risk
AUTH_KEY_DUPLICATED — Telegram revoking the key."""

import os
import sys
import time

try:
    import fcntl
except ImportError:  # Windows: no flock — the guard is a no-op there
    fcntl = None  # type: ignore[assignment]

_held: dict = {}

# How long a starting process waits for the session: the panel stops the
# previous holder and starts the next unit at once (systemd runs the two jobs
# in parallel), and the old process needs a few seconds to shut down.
WAIT_SEC = 30


class SessionBusy(RuntimeError):
    pass


def lock_session(session_file: str, wait: float | None = None) -> None:
    """Take the session's lock, waiting up to ``wait`` seconds (``WAIT_SEC``)
    for it, or raise ``SessionBusy`` naming the holder."""
    if fcntl is None:
        return
    path = f"{session_file}.lock"
    if path in _held:
        return
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    deadline = time.monotonic() + (WAIT_SEC if wait is None else wait)
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.monotonic() < deadline:
                time.sleep(1)
                continue
        holder = os.pread(fd, 300, 0).decode(errors="replace").strip()
        os.close(fd)
        raise SessionBusy(
            f"Session {session_file} is in use by another process "
            f"({holder or 'unknown'}) — stop it first."
        ) from None
    os.ftruncate(fd, 0)
    os.pwrite(fd, f"pid {os.getpid()}: {' '.join(sys.argv)}".encode(), 0)
    _held[path] = fd  # kept open: the lock lives as long as the process
