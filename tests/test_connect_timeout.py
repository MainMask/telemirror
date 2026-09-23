"""A5: a hanging ``client.connect()`` must fail with a bounded timeout, not spin
forever."""

import asyncio
import logging
import time

import pytest

from telemirror.mirroring import Mirroring
from telemirror.misc.telegram_client import cancel_and_await, connect_with_timeout
from telemirror.storage import InMemoryDatabase
from tests.conftest import run


class HangingClient:
    def is_connected(self):
        return False

    async def connect(self):
        await asyncio.Event().wait()  # never resolves

    async def disconnect(self):
        pass


def test_connect_times_out(monkeypatch):
    monkeypatch.setattr(Mirroring, "CONNECT_TIMEOUT_SEC", 0.2)
    db = run(InMemoryDatabase())
    m = Mirroring(
        chat_mapping={},
        database=db,
        receiver=object(),
        sender=object(),
        logger=logging.getLogger("test"),
    )

    started = time.monotonic()
    with pytest.raises(RuntimeError, match="Timeout error while connecting"):
        run(m._Mirroring__connect_client(HangingClient()))
    assert time.monotonic() - started < 5


class _CancelObservingClient:
    """Like HangingClient, but connect() records whether it was actually
    cancelled instead of left running."""

    def __init__(self):
        self.cancelled = False

    def is_connected(self):
        return False

    async def connect(self):
        try:
            await asyncio.Event().wait()  # never resolves on its own
        except asyncio.CancelledError:
            self.cancelled = True
            raise


def test_cancelling_connect_with_timeout_cancels_the_background_connect_task():
    """SIGTERM during a slow handshake cancels whatever task is awaiting
    connect_with_timeout — the background connection_task it spawned must be
    cancelled too, not leaked to race a later client.disconnect()."""

    async def scenario():
        client = _CancelObservingClient()
        task = asyncio.ensure_future(connect_with_timeout(client, timeout_sec=30))
        # Let the task start and reach the polling loop's first sleep.
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        # Give the now-cancelled connection_task a turn to actually deliver
        # CancelledError into client.connect().
        await asyncio.sleep(0)
        assert client.cancelled

    run(scenario())


class _FailsImmediatelyClient:
    """connect() raises a real (non-cancellation) exception with no internal
    await — it runs to completion on its very first turn, independent of
    whatever happens to the caller."""

    def is_connected(self):
        return False

    async def connect(self):
        raise ConnectionResetError("boom")


def test_cancelling_connect_with_timeout_still_raises_cancelled_when_connection_task_independently_failed():
    """If connection_task happens to finish with its own unrelated exception
    in the same window the caller is cancelled, connect_with_timeout must
    still raise CancelledError (the graceful-shutdown contract) — not leak
    connection_task's own exception instead."""

    async def scenario():
        client = _FailsImmediatelyClient()
        task = asyncio.ensure_future(connect_with_timeout(client, timeout_sec=30))
        # Let connect_with_timeout start and enter the polling loop's sleep.
        await asyncio.sleep(0)
        # Let connection_task run to completion (raises, stored, unconsumed)
        # while the outer task is still suspended in that same sleep.
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    run(scenario())


async def _raises_value_error():
    raise ValueError("boom")


def test_cancel_and_await_logs_a_swallowed_non_cancellation_exception(caplog):
    """A real bug in a task cancel_and_await tears down (e.g. watchdog_task)
    must not vanish without a trace — only its own CancelledError is
    silently swallowed."""

    async def scenario():
        task = asyncio.ensure_future(_raises_value_error())
        await asyncio.sleep(0)  # let it run to completion before cancelling
        await cancel_and_await(task)  # must not raise

    with caplog.at_level(logging.WARNING, logger="telemirror.misc.telegram_client"):
        run(scenario())

    assert any(
        "ValueError" in r.message and "boom" in r.message for r in caplog.records
    )


def test_cancel_and_await_does_not_log_a_plain_cancellation(caplog):
    async def _hangs():
        await asyncio.Event().wait()

    async def scenario():
        task = asyncio.ensure_future(_hangs())
        await asyncio.sleep(0)
        await cancel_and_await(task)

    with caplog.at_level(logging.WARNING, logger="telemirror.misc.telegram_client"):
        run(scenario())

    assert not caplog.records


def test_cancel_and_await_absorbs_a_second_cancellation_of_its_caller():
    """A second SIGTERM (signals.py's persistent handler calls task.cancel()
    on every one received) landing while __connect_client's finally block is
    inside `await cancel_and_await(watchdog_task)` must not skip the
    remaining cleanup after it (sdnotify STOPPING / client.disconnect() in
    mirroring.py) — same contract the old plain try/except around a bare
    `await watchdog_task` gave for free."""
    async def _hangs():
        await asyncio.Event().wait()

    async def scenario():
        task = asyncio.ensure_future(_hangs())
        await asyncio.sleep(0)  # let it start
        # Simulate a second SIGTERM: cancel the CALLING task itself while
        # it's about to be suspended inside cancel_and_await's own await.
        asyncio.get_running_loop().call_soon(asyncio.current_task().cancel)
        await cancel_and_await(task)  # must not raise/propagate that cancellation
        return "cleanup ran"

    assert run(scenario()) == "cleanup ran"
