"""telemirror.alert: message shape, and it never fails the OnFailure chain."""

import pytest

from telemirror import alert
from tests.conftest import run


def test_message_contains_unit_host_and_journal(monkeypatch):
    monkeypatch.setattr(alert, "_journal_tail", lambda unit, lines=15: "boom\ntrace")
    msg = alert._message("telemirror.service")
    assert "telemirror.service" in msg
    assert "boom\ntrace" in msg
    assert "failed state" in msg


def test_send_skips_without_tech_channel(monkeypatch):
    monkeypatch.setattr(alert, "_env", lambda key, default=None: default)

    def _no_client(*a, **k):
        raise AssertionError("must not build a client without TECH_CHANNEL")

    monkeypatch.setattr(alert, "TelegramClient", _no_client)
    assert run(alert._send("telemirror.service")) == 0


def test_main_swallows_errors(monkeypatch):
    monkeypatch.setattr(alert.sys, "argv", ["alert", "telemirror.service"])

    async def _boom(unit):
        raise RuntimeError("telegram unreachable")

    monkeypatch.setattr(alert, "_send", _boom)
    with pytest.raises(SystemExit) as e:
        alert.main()
    assert e.value.code == 0
