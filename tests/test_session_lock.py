"""One process per session: a second process on the same .jsession refuses to
start instead of splitting updates / triggering AUTH_KEY_DUPLICATED."""

import subprocess
import sys
from pathlib import Path

import pytest

from telemirror.misc import session_lock

REPO_ROOT = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(session_lock.fcntl is None, reason="no flock on this OS")

HOLD = (
    "import sys, time; from telemirror.misc.session_lock import lock_session; "
    "lock_session(sys.argv[1]); print('locked', flush=True); time.sleep(30)"
)
TRY = (
    "import sys; from telemirror.misc.session_lock import lock_session, SessionBusy\n"
    "try:\n    lock_session(sys.argv[1], wait=float(sys.argv[2])); print('ok')\n"
    "except SessionBusy as e:\n    print('busy:', e)"
)


def _run(code, session, wait=0):
    return subprocess.run(
        [sys.executable, "-c", code, str(session), str(wait)],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout


def test_second_process_on_the_same_session_is_refused(tmp_path):
    session = tmp_path / "a.jsession"
    holder = subprocess.Popen(
        [sys.executable, "-c", HOLD, str(session)], cwd=REPO_ROOT, stdout=subprocess.PIPE, text=True
    )
    try:
        assert holder.stdout.readline().strip() == "locked"
        out = _run(TRY, session)
        assert out.startswith("busy:")
        assert f"pid {holder.pid}" in out
        assert _run(TRY, tmp_path / "other.jsession").strip() == "ok"
    finally:
        holder.kill()
        holder.wait()
        holder.stdout.close()
    # The lock dies with its process — the session is free again.
    assert _run(TRY, session).strip() == "ok"


def test_a_starting_process_waits_for_the_previous_one_to_exit(tmp_path):
    """The panel stops the old holder and starts the next unit at once: the new
    process must wait for the session instead of failing on it."""
    session = tmp_path / "a.jsession"
    holder = subprocess.Popen(
        [sys.executable, "-c", HOLD.replace("time.sleep(30)", "time.sleep(2)"), str(session)],
        cwd=REPO_ROOT, stdout=subprocess.PIPE, text=True,
    )
    try:
        assert holder.stdout.readline().strip() == "locked"
        assert _run(TRY, session, wait=15).strip() == "ok"
    finally:
        holder.kill()
        holder.wait()
        holder.stdout.close()


def test_locking_twice_in_one_process_is_fine(tmp_path):
    session = str(tmp_path / "a.jsession")
    session_lock.lock_session(session)
    session_lock.lock_session(session)
