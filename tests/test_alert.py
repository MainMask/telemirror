"""telemirror.alert: message shape, and send_alert never raises."""

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
    alert.send_alert("hi")  # returns, does not raise


def test_send_alert_swallows_errors(monkeypatch):
    async def _boom(text):
        raise RuntimeError("telegram unreachable")

    monkeypatch.setattr(alert, "_connect_and_send", _boom)
    alert.send_alert("hi")  # swallowed
