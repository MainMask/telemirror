"""systemctl/journalctl adapter: parsing and the unit whitelist (no real systemd)."""

import pytest

from telemirror.panel import settings
from telemirror.panel.systemd import Systemd, SystemdError, parse_show
from tests.conftest import run

SHOW_ACTIVE = """\
ActiveState=active
SubState=running
Result=success
ActiveEnterTimestamp=@1763380000
InactiveEnterTimestamp=@1763370000
NRestarts=3
MemoryCurrent=524288000
InvocationID=0123456789abcdef0123456789abcdef
LoadState=loaded
"""

SHOW_NEVER_RAN = """\
ActiveState=inactive
SubState=dead
Result=success
ActiveEnterTimestamp=
InactiveEnterTimestamp=
NRestarts=0
MemoryCurrent=[not set]
InvocationID=
LoadState=loaded
"""


def test_parse_show_active():
    st = parse_show(SHOW_ACTIVE)
    assert st.running and st.active == "active" and st.sub == "running"
    assert st.since == 1763380000  # ActiveEnterTimestamp while active
    assert st.restarts == 3 and st.memory == 524288000 and st.loaded
    assert st.invocation == "0123456789abcdef0123456789abcdef"


def test_parse_show_never_ran():
    st = parse_show(SHOW_NEVER_RAN)
    assert not st.running and st.since is None and st.memory is None and st.invocation == ""


class _Recorder:
    def __init__(self, rc=0, out=""):
        self.calls: list = []
        self.rc, self.out = rc, out

    async def __call__(self, argv):
        self.calls.append(list(argv))
        return self.rc, self.out


def test_commands_use_no_block_and_whitelist():
    rec = _Recorder(out=SHOW_ACTIVE)
    sd = Systemd(runner=rec)
    run(sd.restart(settings.LIVE_UNIT))
    run(sd.show(settings.COURSES_UNIT))
    run(sd.journal(settings.UNITS["sp"], 15, invocation="abc", grep=r"\[Progress\]"))
    assert rec.calls[0] == ["systemctl", "--no-block", "restart", "telemirror.service"]
    assert rec.calls[1][:4] == ["systemctl", "show", "telemirror-past-courses.service", "--timestamp=unix"]
    assert rec.calls[2] == [
        "journalctl", "-u", "telemirror-task@sync_pins.service", "-n", "15", "--no-pager",
        "-o", "cat", "_SYSTEMD_INVOCATION_ID=abc", "--grep", r"\[Progress\]",
    ]
    with pytest.raises(ValueError):
        run(sd.stop("sshd.service"))
    with pytest.raises(ValueError):
        run(sd.journal("telemirror.service; rm -rf /", 1))


def test_errors_surface():
    sd = Systemd(runner=_Recorder(rc=1, out="Access denied"))
    with pytest.raises(SystemdError, match="Access denied"):
        run(sd.start(settings.LIVE_UNIT))
    # journalctl --grep with no match exits 1 — that's "no lines", not an error
    assert run(Systemd(runner=_Recorder(rc=1, out="")).journal(settings.LIVE_UNIT, 5, grep="x")) == ""
