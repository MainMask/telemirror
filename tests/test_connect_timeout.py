"""A5: a hanging ``client.connect()`` must fail with a bounded timeout, not spin
forever."""

import asyncio
import logging
import time

import pytest

from telemirror.mirroring import Mirroring
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
