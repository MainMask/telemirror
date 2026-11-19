"""safe_call must give up on transport errors after max_retries instead of
retrying forever."""

import pytest

from telemirror.tasks._common import safe_call
from tests.conftest import run


async def _noop(*_a, **_kw):
    pass


class _Client:
    def is_connected(self):
        return True

    async def connect(self):
        pass

    async def disconnect(self):
        pass


def test_transport_error_reraised_after_max_retries(monkeypatch):
    monkeypatch.setattr("asyncio.sleep", _noop)
    calls = 0

    async def always_fails():
        nonlocal calls
        calls += 1
        raise OSError("boom")

    with pytest.raises(OSError):
        run(safe_call(_Client(), always_fails, max_retries=3))
    assert calls == 4  # initial try + 3 retries


def test_success_returns_result(monkeypatch):
    monkeypatch.setattr("asyncio.sleep", _noop)

    async def ok():
        return 42

    assert run(safe_call(_Client(), ok)) == 42


def test_flood_wait_is_waited_out_without_a_reconnect(monkeypatch):
    from telethon.errors import FloodWaitError

    slept = []

    async def sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr("asyncio.sleep", sleep)
    client = _Client()
    disconnects = []

    async def disconnect():
        disconnects.append(1)

    client.disconnect = disconnect
    answers = iter([FloodWaitError(request=None, capture=42), "ok"])

    async def fn():
        answer = next(answers)
        if isinstance(answer, Exception):
            raise answer
        return answer

    assert run(safe_call(client, fn)) == "ok"
    assert slept[0] == 42 and disconnects == []
