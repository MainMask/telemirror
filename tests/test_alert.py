"""telemirror.alert: message shape, and send_alert never raises."""

import io
import json

import pytest

from telemirror import alert


@pytest.fixture(autouse=True)
def _no_bot_from_dotenv(monkeypatch):
    """A developer's real .env may hold PANEL_BOT_TOKEN — never let a test
    reach the real Bot API through it."""
    real = alert._env
    monkeypatch.setattr(
        alert, "_env",
        lambda key, default=None: default if key.startswith("PANEL_") else real(key, default=default),
    )


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


def _bot_env(monkeypatch, admins="111, 222"):
    env = {"PANEL_BOT_TOKEN": "123:abc", "PANEL_ADMIN_IDS": admins}
    monkeypatch.setattr(alert, "_env", lambda key, default=None: env.get(key, default))


def test_send_alert_goes_through_the_bot_to_every_admin(monkeypatch):
    _bot_env(monkeypatch)
    sent = []

    def _urlopen(request, timeout):
        sent.append((request.full_url, json.loads(request.data)))
        return io.BytesIO(b'{"ok": true}')

    monkeypatch.setattr(alert.urllib.request, "urlopen", _urlopen)

    async def _no_userbot(text):
        raise AssertionError("with a bot token the userbot session must not be used")

    monkeypatch.setattr(alert, "_connect_and_send", _no_userbot)
    assert alert.send_alert("down") is True
    assert [body["chat_id"] for _, body in sent] == [111, 222]
    assert all(url.endswith("/bot123:abc/sendMessage") for url, _ in sent)
    assert sent[0][1]["text"].startswith("down")


def test_bot_alert_counts_as_delivered_if_any_admin_got_it(monkeypatch):
    _bot_env(monkeypatch)

    def _urlopen(request, timeout):
        if json.loads(request.data)["chat_id"] == 111:
            raise OSError("blocked")
        return io.BytesIO(b'{"ok": true}')

    monkeypatch.setattr(alert.urllib.request, "urlopen", _urlopen)
    assert alert.send_alert("down") is True


def test_bot_alert_fails_when_no_admin_got_it(monkeypatch):
    _bot_env(monkeypatch)

    def _urlopen(request, timeout):
        raise OSError("network down")

    monkeypatch.setattr(alert.urllib.request, "urlopen", _urlopen)
    assert alert.send_alert("down") is False
