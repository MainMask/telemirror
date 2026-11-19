"""telemirror.past under Type=notify: READY=1 at once (a run with nothing to
replay is not a failed start), and the watchdog pinged only while the
account's connection is alive — a dead one gets the unit restarted."""

import asyncio
import contextlib
import logging

import pytest

from telemirror import past
from telemirror.directions import DirectionConfig, PastModeConfig
from telemirror.messagefilters import EmptyMessageFilter
from telemirror.misc import sdnotify, telegram_client
from telemirror.storage import InMemoryDatabase
from tests.conftest import run

_LOG = logging.getLogger("test.past_watchdog")


class _Client:
    def __init__(self, connected):
        self.connected = connected

    def is_connected(self):
        return self.connected

    async def __call__(self, request):  # updates.GetState
        return object()


def _wire(monkeypatch, client, pairs=True):
    sent = []
    monkeypatch.setattr(sdnotify, "notify", lambda state: sent.append(state) or True)
    monkeypatch.setattr(sdnotify, "watchdog_interval", lambda: 0.01)
    cfg = DirectionConfig(disable_delete=False, disable_edit=False, filters=EmptyMessageFilter(),
                          past_mode=PastModeConfig(full_history=True))
    monkeypatch.setattr(past, "CHAT_MAPPING", {-1001: {-1002: [cfg]}} if pairs else {})

    async def database(url, logger):
        return await InMemoryDatabase()

    @contextlib.asynccontextmanager
    async def account(logger, **kw):
        yield client, object()

    async def replay(*a):
        await asyncio.sleep(0.1)  # a few watchdog intervals

    monkeypatch.setattr(past, "open_database", database)
    monkeypatch.setattr(past, "open_account", account)
    monkeypatch.setattr(past, "_replay_all", replay)
    return sent


def test_a_live_connection_feeds_the_watchdog(monkeypatch):
    sent = _wire(monkeypatch, _Client(connected=True))
    run(past._run(_LOG))
    assert sent[0] == "READY=1" and "WATCHDOG=1" in sent and sent[-1] == "STOPPING=1"


def test_a_dead_connection_starves_the_watchdog(monkeypatch):
    # connection_probe's grace is read when the probe is made: 0 → unhealthy at once
    monkeypatch.setattr(past, "connection_probe",
                        lambda client, log: telegram_client.connection_probe(client, log, grace_sec=0))
    sent = _wire(monkeypatch, _Client(connected=False))
    run(past._run(_LOG))
    assert "READY=1" in sent and "WATCHDOG=1" not in sent


def test_nothing_to_replay_is_still_a_clean_start(monkeypatch):
    sent = _wire(monkeypatch, _Client(connected=True), pairs=False)
    run(past._run(_LOG))
    assert sent == ["READY=1"]


def test_a_stopped_replay_exits_143_not_0(monkeypatch):
    """SIGTERM (⏹, Conflicts=) cancels the replay mid-request: it shuts down
    cleanly and exits STOPPED_EXIT — the unit's SuccessExitStatus, but not 0
    (the panel would report a finished replay)."""

    class _Stopped(_Client):
        async def get_messages(self, *a, **kw):
            raise asyncio.CancelledError  # what cancel_on_sigterm delivers

    real_replay_all = past._replay_all
    sent = _wire(monkeypatch, _Stopped(connected=True))
    monkeypatch.setattr(past, "_replay_all", real_replay_all)
    monkeypatch.setattr(past, "cancel_on_sigterm", lambda: None)
    monkeypatch.setattr(past, "_configure_logging", lambda level: _LOG)
    with pytest.raises(SystemExit) as e:
        past.main()
    assert e.value.code == past.STOPPED_EXIT == 143
    assert sent[-1] == "STOPPING=1"
