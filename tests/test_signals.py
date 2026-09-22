"""cancel_on_sigterm must not crash at startup on Windows (add_signal_handler
raises NotImplementedError there), while still registering the real handler
on the platforms production actually runs on (systemd = Linux)."""

import asyncio

from telemirror.misc import signals
from tests.conftest import run


def test_cancel_on_sigterm_is_a_noop_on_windows(monkeypatch):
    monkeypatch.setattr(signals.sys, "platform", "win32")

    def _must_not_be_called(*args, **kwargs):
        raise AssertionError("add_signal_handler must not be called on Windows")

    async def scenario():
        loop = asyncio.get_running_loop()
        monkeypatch.setattr(loop, "add_signal_handler", _must_not_be_called)
        signals.cancel_on_sigterm()  # must not raise

    run(scenario())


def test_cancel_on_sigterm_registers_sigterm_handler_on_linux(monkeypatch):
    monkeypatch.setattr(signals.sys, "platform", "linux")
    registered = []

    async def scenario():
        loop = asyncio.get_running_loop()
        monkeypatch.setattr(
            loop, "add_signal_handler", lambda sig, cb: registered.append((sig, cb))
        )
        signals.cancel_on_sigterm()
        task = asyncio.current_task()
        assert registered == [(signals.signal.SIGTERM, task.cancel)]

    run(scenario())
