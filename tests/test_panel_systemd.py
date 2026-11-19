"""systemctl/journalctl adapter: parsing and the unit whitelist (no real systemd)."""

import pytest

from bot.systemd import Systemd, SystemdError, parse_show
from telemirror import projects
from tests.conftest import run


@pytest.fixture
def demo(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(projects, "REPO_DIR", tmp_path)
    return projects.create_project("Демо", "🧪", "s.jsession")

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
    assert st.restarts == 3 and st.memory == 524288000
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


def test_commands_use_no_block_and_whitelist(demo):
    rec = _Recorder(out=SHOW_ACTIVE)
    sd = Systemd(runner=rec)
    run(sd.restart(demo.live_unit))
    run(sd.show(demo.past_unit))
    run(sd.journal(demo.task_unit, 15, invocation="abc", grep=r"\[Progress\]"))
    run(sd.show("telemirror-health.timer"))
    assert rec.calls[0] == ["systemctl", "--no-block", "restart", "telemirror@demo.service"]
    assert rec.calls[1][:4] == ["systemctl", "show", "telemirror-past@demo.service", "--timestamp=unix"]
    assert rec.calls[2] == [
        "journalctl", "-u", "telemirror-task@demo.service", "-n", "15", "--no-pager",
        "-o", "cat", "_SYSTEMD_INVOCATION_ID=abc", "--grep", r"\[Progress\]",
    ]
    with pytest.raises(ValueError):
        run(sd.stop("sshd.service"))
    with pytest.raises(ValueError):
        run(sd.stop("telemirror@other.service"))  # no such project
    with pytest.raises(ValueError):
        run(sd.journal("telemirror@demo.service; rm -rf /", 1))


def test_errors_surface(demo):
    sd = Systemd(runner=_Recorder(rc=1, out="Access denied"))
    with pytest.raises(SystemdError, match="Access denied"):
        run(sd.start(demo.live_unit))
    # journalctl --grep with no match exits 1 — that's "no lines", not an error
    assert run(Systemd(runner=_Recorder(rc=1, out="")).journal(demo.live_unit, 5, grep="x")) == ""
