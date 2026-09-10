"""telemirror.misc.sdnotify: no-op without NOTIFY_SOCKET, real datagram with it,
watchdog loop pings only while alive."""

import asyncio
import socket
import tempfile
from pathlib import Path

from telemirror.misc import sdnotify
from tests.conftest import run


def test_notify_noop_without_socket(monkeypatch):
    monkeypatch.delenv("NOTIFY_SOCKET", raising=False)
    assert sdnotify.notify("READY=1") is False


def test_notify_sends_datagram(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        path = str(Path(d) / "notify.sock")
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        srv.bind(path)
        srv.settimeout(2)
        try:
            monkeypatch.setenv("NOTIFY_SOCKET", path)
            assert sdnotify.notify("READY=1") is True
            assert srv.recv(64) == b"READY=1"
        finally:
            srv.close()


def test_watchdog_interval(monkeypatch):
    monkeypatch.delenv("WATCHDOG_USEC", raising=False)
    assert sdnotify.watchdog_interval() is None
    monkeypatch.setenv("WATCHDOG_USEC", "6000000")  # 6s WatchdogSec
    assert sdnotify.watchdog_interval() == 3.0
    monkeypatch.setenv("WATCHDOG_USEC", "nonsense")
    assert sdnotify.watchdog_interval() is None


def test_watchdog_loop_pings_only_while_probe_ok(monkeypatch):
    monkeypatch.setattr(sdnotify, "watchdog_interval", lambda: 0.0)
    pings = []
    monkeypatch.setattr(sdnotify, "notify", lambda state: pings.append(state))

    healthy = {"v": True}

    async def probe():
        return healthy["v"]

    async def go():
        task = asyncio.create_task(sdnotify.watchdog_loop(probe))
        await asyncio.sleep(0.05)          # several ticks while healthy
        healthy["v"] = False
        stopped_at = len(pings)
        await asyncio.sleep(0.05)          # ticks while unhealthy
        task.cancel()
        return stopped_at

    stopped_at = run(go())
    assert stopped_at > 0
    assert pings == ["WATCHDOG=1"] * stopped_at   # nothing added after probe→False


def test_watchdog_loop_probe_exception_withholds_ping(monkeypatch):
    monkeypatch.setattr(sdnotify, "watchdog_interval", lambda: 0.0)
    pings = []
    monkeypatch.setattr(sdnotify, "notify", lambda state: pings.append(state))

    async def probe():
        raise RuntimeError("wedged")

    async def go():
        task = asyncio.create_task(sdnotify.watchdog_loop(probe))
        await asyncio.sleep(0.05)
        task.cancel()

    run(go())
    assert pings == []


def test_watchdog_loop_returns_immediately_without_watchdog(monkeypatch):
    monkeypatch.setattr(sdnotify, "watchdog_interval", lambda: None)
    calls = []
    monkeypatch.setattr(sdnotify, "notify", lambda state: calls.append(state))

    async def probe():
        return True

    run(sdnotify.watchdog_loop(probe))
    assert calls == []
