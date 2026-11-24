"""telemirror.notify: notices to the panel's admins through its bot."""

import io
import json

import pytest

from bot.callbacks import NavCB
from telemirror import notify, projects
from telemirror.notify import BotNotifier
from tests.conftest import run


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    """A developer's real .env may hold PANEL_BOT_TOKEN — tests set their own."""
    env: dict = {}
    monkeypatch.setattr(notify, "_env", lambda key, default=None: env.get(key, default))
    return env


def test_admins_are_parsed_leniently():
    assert notify.parse_admins("111, 222;333,,bad") == [111, 222, 333]


def test_no_bot_no_notifier(_env):
    assert BotNotifier.from_env("live") is None
    _env["PANEL_BOT_TOKEN"] = "1:x"
    assert BotNotifier.from_env("live") is None  # nobody to tell
    _env["PANEL_ADMIN_IDS"] = "111"
    assert BotNotifier.from_env("live") is not None


def test_the_button_is_the_panels_unit_screen():
    for n, kind in enumerate(notify.UNIT_KINDS):
        packed = notify.unit_button("live", kind)["inline_keyboard"][0][0]
        assert packed["callback_data"] == NavCB(s="unit", p="live", i=n).pack()
    from bot.registry import TITLES
    assert notify.BUTTON == TITLES["notice"]


def test_a_projects_notice_is_signed_with_it(tmp_path, monkeypatch, _env):
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(projects, "REPO_DIR", tmp_path)
    project = projects.create_project("Зеркало", "🪞", "sessions/a.jsession")
    _env.update(PANEL_BOT_TOKEN="1:x", PANEL_ADMIN_IDS="111")
    assert BotNotifier.from_env(project.key).text("упало") == "🪞 Зеркало: упало"
    assert BotNotifier.from_env("gone").text("упало") == "gone: упало"


def test_send_sync_reaches_every_admin_as_plain_text(monkeypatch):
    sent = []

    def _urlopen(request, timeout):
        sent.append((request.full_url, json.loads(request.data)))
        if sent[-1][1]["chat_id"] == 111:
            raise OSError("blocked")
        return io.BytesIO(b'{"ok": true}')

    monkeypatch.setattr(notify.urllib.request, "urlopen", _urlopen)
    n = BotNotifier("1:x", [111, 222], "🪞 Зеркало", notify.unit_button("live", "live"))
    assert n.send_sync("**x** " + "y" * 5000) is True  # one admin got it
    assert [body["chat_id"] for _, body in sent] == [111, 222]
    body = sent[1][1]
    assert sent[1][0].endswith("/bot1:x/sendMessage")
    assert "parse_mode" not in body  # log lines and names are never markup
    assert len(body["text"].encode("utf-16-le")) // 2 == notify.MAX_TEXT  # Telegram counts UTF-16 units
    assert body["text"].startswith("🪞 Зеркало: **x**")
    assert body["reply_markup"]["inline_keyboard"][0][0]["text"] == "📊 Статус и журнал"


def test_send_never_raises(monkeypatch):
    class Broken:
        def __init__(self, *a, **k):
            raise RuntimeError("no network")

    monkeypatch.setattr(notify.aiohttp, "ClientSession", Broken)
    assert run(BotNotifier("1:x", [111]).send("hi")) is False


def test_cut_counts_utf16_units():
    assert notify.cut("abc", 3) == "abc"
    assert notify.cut("🪞🪞", 3) == "🪞"  # each is two units: a second one won't fit
    assert notify.cut("🪞🪞", 4) == "🪞🪞"
    assert notify.cut("я" * 10, 4) == "яяяя"  # BMP: one unit each
