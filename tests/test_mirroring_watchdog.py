"""Mirroring.__watchdog_probe: healthy only when connected AND a bounded
updates.GetState round-trip succeeds; a disconnect is tolerated for a grace
window so telethon's auto-reconnect gets a chance."""

import asyncio
import logging

from telemirror.mirroring import Mirroring
from tests.conftest import run

SRC = -1001
TGT = -1002


class _Client:
    def __init__(self, connected=True, state_ok=True, state_hang=False):
        self._connected = connected
        self._state_ok = state_ok
        self._state_hang = state_hang
        self.state_calls = 0

    def is_connected(self):
        return self._connected

    async def __call__(self, request):
        self.state_calls += 1
        if self._state_hang:
            await asyncio.sleep(9999)
        if not self._state_ok:
            raise RuntimeError("GetState failed")
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


def test_unhealthy_when_state_errors():
    assert run(_probe(_Client(state_ok=False))()) is False


def test_unhealthy_when_state_hangs(monkeypatch):
    monkeypatch.setattr(Mirroring, "WATCHDOG_PROBE_TIMEOUT_SEC", 0.01)
    assert run(_probe(_Client(state_hang=True))()) is False


def test_disconnect_within_grace_is_tolerated(monkeypatch):
    monkeypatch.setattr(Mirroring, "WATCHDOG_DISCONNECT_GRACE_SEC", 100)
    probe = _probe(_Client(connected=False))
    assert run(probe()) is True   # first miss — within grace


def test_disconnect_past_grace_gives_up(monkeypatch):
    monkeypatch.setattr(Mirroring, "WATCHDOG_DISCONNECT_GRACE_SEC", 0)
    probe = _probe(_Client(connected=False))
    assert run(probe()) is False
