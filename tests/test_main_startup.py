"""run_telemirror starts the health endpoint and opens the database
concurrently (asyncio.gather). With the default return_exceptions=False,
gather() would propagate the first failure without cancelling the other
awaitable — so if the DB side succeeds after the health side already raised,
the opened database would never be assigned anywhere and so never closed.
This must not leak: whichever side succeeds must still be closed before the
failure propagates."""

import logging

import pytest

from telemirror import live
from telemirror.storage import InMemoryDatabase
from tests.conftest import run


def test_db_is_closed_when_health_endpoint_fails_after_db_opens(monkeypatch):
    closed = []

    async def fake_close(self):
        closed.append(self)

    monkeypatch.setattr(InMemoryDatabase, "close", fake_close)

    async def failing_health_endpoint(host, port):
        raise RuntimeError("port already in use")

    monkeypatch.setattr(live, "serve_health_endpoint", failing_health_endpoint)

    with pytest.raises(RuntimeError, match="port already in use"):
        run(
            live.run_telemirror(
                db_url=None,
                api_id="1",
                api_hash="x",
                api_device_model=None,
                api_system_version=None,
                api_app_version=None,
                session_string="x",
                chat_mapping={},
                logger=logging.getLogger("test.mainstartup"),
                host="127.0.0.1",
                port=0,
            )
        )

    assert len(closed) == 1


def test_db_failure_propagates_and_health_failure_is_logged_when_both_fail(
    monkeypatch, caplog
):
    """If the health endpoint AND the database open both fail concurrently,
    the DB exception must still propagate (existing behavior, nothing to
    close), but the health exception must not be silently dropped — it's
    logged so an operator debugging the crash from journald can see both."""

    async def failing_init(self):
        raise RuntimeError("bad DSN")

    monkeypatch.setattr(InMemoryDatabase, "_async__init__", failing_init)

    async def failing_health_endpoint(host, port):
        raise OSError("port already in use")

    monkeypatch.setattr(live, "serve_health_endpoint", failing_health_endpoint)

    with caplog.at_level(logging.ERROR, logger="test.mainstartup"):
        with pytest.raises(RuntimeError, match="bad DSN"):
            run(
                live.run_telemirror(
                    db_url=None,
                    api_id="1",
                    api_hash="x",
                    api_device_model=None,
                    api_system_version=None,
                    api_app_version=None,
                    session_string="x",
                    chat_mapping={},
                    logger=logging.getLogger("test.mainstartup"),
                    host="127.0.0.1",
                    port=0,
                )
            )

    assert any(
        "port already in use" in record.message for record in caplog.records
    )


def _kwargs():
    return {
        "db_url": None, "api_id": "1", "api_hash": "x", "api_device_model": None,
        "api_system_version": None, "api_app_version": None, "session_string": "x",
        "chat_mapping": {}, "logger": logging.getLogger("test.mainstartup"),
        "host": "127.0.0.1", "port": 0,
    }


class _Runner:
    cleaned = 0

    async def cleanup(self):
        _Runner.cleaned += 1


def test_db_and_health_are_closed_when_the_mirror_fails_to_build(monkeypatch):
    """Telemirror(...) raising (a bad session string…) must still close the
    opened database and stop the health endpoint."""
    closed = []

    async def fake_close(self):
        closed.append(self)

    async def health(host, port):
        return _Runner()

    def broken(**kwargs):
        raise ValueError("bad session")

    monkeypatch.setattr(InMemoryDatabase, "close", fake_close)
    monkeypatch.setattr(live, "serve_health_endpoint", health)
    monkeypatch.setattr(live, "Telemirror", broken)
    _Runner.cleaned = 0
    with pytest.raises(ValueError, match="bad session"):
        run(live.run_telemirror(**_kwargs()))
    assert len(closed) == 1 and _Runner.cleaned == 1


def test_health_endpoint_is_stopped_when_the_database_fails(monkeypatch):
    async def failing_init(self):
        raise RuntimeError("bad DSN")

    async def health(host, port):
        return _Runner()

    monkeypatch.setattr(InMemoryDatabase, "_async__init__", failing_init)
    monkeypatch.setattr(live, "serve_health_endpoint", health)
    _Runner.cleaned = 0
    with pytest.raises(RuntimeError, match="bad DSN"):
        run(live.run_telemirror(**_kwargs()))
    assert _Runner.cleaned == 1
