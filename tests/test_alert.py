"""telemirror.alert: message shape, and send_alert never raises."""

import pytest

from telemirror import alert


def test_failed_state_message_has_unit_and_journal(monkeypatch):
    monkeypatch.setattr(alert, "journal_tail", lambda unit, lines=15: "boom\ntrace")
    msg = alert._failed_state_message("telemirror.service")
    assert "telemirror.service" in msg
    assert "boom\ntrace" in msg
    assert "failed state" in msg


def test_send_alert_skips_without_tech_channel(monkeypatch):
    monkeypatch.setattr(alert, "_env", lambda key, default=None: default)

    def _no_client(*a, **k):
        raise AssertionError("must not build a client without TECH_CHANNEL")

    monkeypatch.setattr(alert, "TelegramClient", _no_client)
    # Deliberately unconfigured is not a failure — must be distinguishable
    # from a real delivery failure (None, not False) so main() doesn't flag
    # the OnFailure unit as failed just because TECH_CHANNEL isn't set.
    assert alert.send_alert("hi") is None


def test_send_alert_swallows_errors(monkeypatch):
    async def _boom(text):
        raise RuntimeError("telegram unreachable")

    monkeypatch.setattr(alert, "_connect_and_send", _boom)
    # swallowed — but must report the failure, not silent success
    assert alert.send_alert("hi") is False


def test_send_alert_returns_true_on_success(monkeypatch):
    async def _ok(text):
        return True

    monkeypatch.setattr(alert, "_connect_and_send", _ok)
    assert alert.send_alert("hi") is True


def test_main_exits_nonzero_when_alert_not_delivered(monkeypatch):
    monkeypatch.setattr(alert, "_failed_state_message", lambda unit: "boom")
    monkeypatch.setattr(alert, "send_alert", lambda text: False)
    monkeypatch.setattr(alert.sys, "argv", ["alert.py", "telemirror.service"])
    with pytest.raises(SystemExit) as exc_info:
        alert.main()
    assert exc_info.value.code != 0


def test_main_exits_zero_when_alert_delivered(monkeypatch):
    monkeypatch.setattr(alert, "_failed_state_message", lambda unit: "boom")
    monkeypatch.setattr(alert, "send_alert", lambda text: True)
    monkeypatch.setattr(alert.sys, "argv", ["alert.py", "telemirror.service"])
    with pytest.raises(SystemExit) as exc_info:
        alert.main()
    assert exc_info.value.code == 0


def test_main_exits_zero_when_tech_channel_not_configured(monkeypatch):
    """Deliberately unconfigured alerting must not make the OnFailure=
    unit itself show up as failed — that's noise, not a real problem."""
    monkeypatch.setattr(alert, "_failed_state_message", lambda unit: "boom")
    monkeypatch.setattr(alert, "send_alert", lambda text: None)
    monkeypatch.setattr(alert.sys, "argv", ["alert.py", "telemirror.service"])
    with pytest.raises(SystemExit) as exc_info:
        alert.main()
    assert exc_info.value.code == 0
