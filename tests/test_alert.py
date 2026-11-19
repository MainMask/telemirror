"""telemirror.alert: message shape, the bot as the only way out, and
send_alert never raises."""

import io
import json

import pytest

from telemirror import alert, notify, projects


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    """A developer's real .env may hold PANEL_BOT_TOKEN — never let a test
    reach the real Bot API through it."""
    env: dict = {}
    monkeypatch.setattr(notify, "_env", lambda key, default=None: env.get(key, default))
    return env


def _bot(env, admins="111, 222"):
    env.update(PANEL_BOT_TOKEN="123:abc", PANEL_ADMIN_IDS=admins)


def test_failed_state_message_has_unit_and_journal(monkeypatch):
    monkeypatch.setattr(alert, "journal_tail", lambda unit, lines=15: "boom\ntrace")
    msg = alert._failed_state_message("telemirror@live.service")
    assert "telemirror@live.service" in msg and "boom\ntrace" in msg
    assert "больше не запустится" in msg


def test_a_failed_task_is_not_said_to_have_given_up_restarting(monkeypatch):
    """A maintenance task is one-shot (no Restart=): it just ended with an error."""
    monkeypatch.setattr(alert, "journal_tail", lambda unit, lines=15: "trace")
    msg = alert._failed_state_message("telemirror-task@demo.service")
    assert "закончил работу с ошибкой" in msg and "больше не запустится" not in msg and "trace" in msg


def test_without_the_bot_there_is_nobody_to_alert(monkeypatch):
    def _no_network(*a, **k):
        raise AssertionError("must not send without PANEL_BOT_TOKEN")

    monkeypatch.setattr(notify.urllib.request, "urlopen", _no_network)
    # Deliberately unconfigured is not a failure — must be distinguishable
    # from a real delivery failure (None, not False) so main() doesn't flag
    # the OnFailure unit as failed just because the bot isn't set up.
    assert alert.send_alert("hi") is None


def test_send_alert_goes_through_the_bot_to_every_admin(monkeypatch, _env):
    _bot(_env)
    sent = []

    def _urlopen(request, timeout):
        sent.append((request.full_url, json.loads(request.data)))
        return io.BytesIO(b'{"ok": true}')

    monkeypatch.setattr(notify.urllib.request, "urlopen", _urlopen)
    assert alert.send_alert("down") is True
    assert [body["chat_id"] for _, body in sent] == [111, 222]
    assert all(url.endswith("/bot123:abc/sendMessage") for url, _ in sent)
    assert sent[0][1]["text"].startswith("down") and "сервер:" in sent[0][1]["text"]


def test_bot_alert_counts_as_delivered_if_any_admin_got_it(monkeypatch, _env):
    _bot(_env)

    def _urlopen(request, timeout):
        if json.loads(request.data)["chat_id"] == 111:
            raise OSError("blocked")
        return io.BytesIO(b'{"ok": true}')

    monkeypatch.setattr(notify.urllib.request, "urlopen", _urlopen)
    assert alert.send_alert("down") is True


def test_bot_alert_fails_when_no_admin_got_it(monkeypatch, _env):
    _bot(_env)

    def _urlopen(request, timeout):
        raise OSError("network down")

    monkeypatch.setattr(notify.urllib.request, "urlopen", _urlopen)
    assert alert.send_alert("down") is False  # a token was set: not "unconfigured"


def test_send_alert_swallows_errors(monkeypatch):
    def _boom(unit):
        raise RuntimeError("broken")

    monkeypatch.setattr(alert, "notifier_of", _boom)
    assert alert.send_alert("hi") is False


def test_a_projects_unit_is_signed_and_has_its_button(tmp_path, monkeypatch, _env):
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(projects, "REPO_DIR", tmp_path)
    project = projects.create_project("Демо", "🚀", "sessions/a.jsession")
    _bot(_env)
    for unit, i in ((project.live_unit, 0), (project.past_unit, 1), (project.task_unit, 2)):
        n = alert.notifier_of(unit)
        assert n.text("x") == "🚀 Демо: x"
        assert n._markup["inline_keyboard"][0][0]["callback_data"] == f"n:unit:{project.key}:{i}:0"
    assert alert.notifier_of("telemirror-panel.service").text("x") == "x"  # not a project's


@pytest.mark.parametrize("sent, code", [(False, 1), (True, 0), (None, 0)])
def test_main_exits_nonzero_only_when_an_alert_was_not_delivered(monkeypatch, sent, code):
    monkeypatch.setattr(alert, "_failed_state_message", lambda unit: "boom")
    monkeypatch.setattr(alert, "send_alert", lambda text, unit: sent)
    monkeypatch.setattr(alert.sys, "argv", ["alert.py", "telemirror@live.service"])
    with pytest.raises(SystemExit) as exc_info:
        alert.main()
    assert exc_info.value.code == code


def test_main_needs_the_unit(monkeypatch):
    monkeypatch.setattr(alert.sys, "argv", ["alert.py"])
    with pytest.raises(SystemExit) as exc_info:
        alert.main()
    assert "usage" in str(exc_info.value.code)


def test_journal_tail_tells_inaccessible_from_empty(monkeypatch):
    import subprocess

    def fake(returncode, stdout, stderr=""):
        return lambda *a, **k: subprocess.CompletedProcess(a, returncode, stdout, stderr)

    monkeypatch.setattr(alert.subprocess, "run", fake(1, "", "No journal files were opened due to insufficient permissions."))
    assert alert.journal_tail("telemirror@live.service").startswith("(журнал недоступен: No journal files")
    monkeypatch.setattr(alert.subprocess, "run", fake(0, ""))
    assert alert.journal_tail("telemirror@live.service") == "(журнал пуст)"
    monkeypatch.setattr(alert.subprocess, "run", fake(0, "line\n"))
    assert alert.journal_tail("telemirror@live.service") == "line"
