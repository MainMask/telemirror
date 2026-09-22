"""run_telemirror starts the health endpoint and opens the database
concurrently (asyncio.gather). With the default return_exceptions=False,
gather() would propagate the first failure without cancelling the other
awaitable — so if the DB side succeeds after the health side already raised,
the opened database would never be assigned anywhere and so never closed.
This must not leak: whichever side succeeds must still be closed before the
failure propagates."""

import logging

import pytest

import main as main_module
from telemirror.storage import InMemoryDatabase
from tests.conftest import run


def test_db_is_closed_when_health_endpoint_fails_after_db_opens(monkeypatch):
    closed = []

    async def fake_close(self):
        closed.append(self)

    monkeypatch.setattr(InMemoryDatabase, "close", fake_close)

    async def failing_health_endpoint(host, port):
        raise RuntimeError("port already in use")

    monkeypatch.setattr(main_module, "serve_health_endpoint", failing_health_endpoint)

    with pytest.raises(RuntimeError, match="port already in use"):
        run(
            main_module.run_telemirror(
                use_memory_db=True,
                db_uri="unused",
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

    monkeypatch.setattr(main_module, "serve_health_endpoint", failing_health_endpoint)

    with caplog.at_level(logging.ERROR, logger="test.mainstartup"):
        with pytest.raises(RuntimeError, match="bad DSN"):
            run(
                main_module.run_telemirror(
                    use_memory_db=True,
                    db_uri="unused",
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
