"""Mirroring.__watchdog_probe: healthy = connected AND a bounded updates.GetState
round-trip succeeds; a few failures in a row are tolerated; FloodWait is not a
hang; a disconnect gets a grace window; long silence only warns."""

import asyncio
import logging

from telethon import errors

from telemirror.mirroring import Mirroring
from tests.conftest import run

SRC = -1001
TGT = -1002


class _Client:
    def __init__(self, connected=True, state_exc=None, state_hang=False):
        self._connected = connected
        self._state_exc = state_exc
        self._state_hang = state_hang
        self.state_calls = 0

    def add_event_handler(self, callback, event=None):
        pass

    def is_connected(self):
        return self._connected

    async def __call__(self, request):
        self.state_calls += 1
        if self._state_hang:
            await asyncio.sleep(9999)
        if self._state_exc is not None:
            raise self._state_exc
        return object()


def _probe(client):
    m = Mirroring(
        chat_mapping={SRC: {TGT: []}},
        database=object(),
        receiver=client,
        sender=client,
        logger=logging.getLogger("test.wd"),
    )
    return m._Mirroring__watchdog_probe(client)


def test_healthy_when_connected_and_state_ok():
    client = _Client()
    assert run(_probe(client)()) is True
    assert client.state_calls == 1


def test_probe_failures_tolerated_until_streak(monkeypatch):
    monkeypatch.setattr(Mirroring, "WATCHDOG_PROBE_FAIL_STREAK", 3)
    probe = _probe(_Client(state_exc=RuntimeError("GetState failed")))

    async def go():
        return [await probe() for _ in range(4)]

    assert run(go()) == [True, True, False, False]


def test_streak_resets_on_success(monkeypatch):
    monkeypatch.setattr(Mirroring, "WATCHDOG_PROBE_FAIL_STREAK", 2)
    client = _Client()
    probe = _probe(client)

    async def go():
        client._state_exc = RuntimeError("x")
        first = await probe()          # fail 1/2 → still True
        client._state_exc = None
        recovered = await probe()      # success resets
        client._state_exc = RuntimeError("x")
        after = await probe()          # fail 1/2 again → still True
        return first, recovered, after

    assert run(go()) == (True, True, True)


def test_floodwait_is_healthy():
    probe = _probe(_Client(state_exc=errors.FloodWaitError(request=None)))
    assert run(probe()) is True


def test_unhealthy_when_state_hangs(monkeypatch):
    monkeypatch.setattr(Mirroring, "WATCHDOG_PROBE_TIMEOUT_SEC", 0.01)
    monkeypatch.setattr(Mirroring, "WATCHDOG_PROBE_FAIL_STREAK", 1)
    assert run(_probe(_Client(state_hang=True))()) is False


def test_disconnect_within_grace_is_tolerated(monkeypatch):
    monkeypatch.setattr(Mirroring, "WATCHDOG_DISCONNECT_GRACE_SEC", 100)
    assert run(_probe(_Client(connected=False))()) is True


def test_disconnect_past_grace_gives_up(monkeypatch):
    monkeypatch.setattr(Mirroring, "WATCHDOG_DISCONNECT_GRACE_SEC", 0)
    assert run(_probe(_Client(connected=False))()) is False


def test_long_silence_warns_but_stays_healthy(monkeypatch, caplog):
    monkeypatch.setattr(Mirroring, "WATCHDOG_SILENCE_WARN_SEC", 0)  # everything is "silent"
    with caplog.at_level(logging.WARNING, logger="test.wd"):
        assert run(_probe(_Client())()) is True
    assert any("no update in" in r.message for r in caplog.records)
