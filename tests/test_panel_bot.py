"""The panel end-to-end through the real Dispatcher (fake Bot API session, fake
systemd, projects and configs in tmp). Buttons are pressed by their labels,
the way an admin does — so labels, callback data and handlers are checked
together."""

import asyncio
import io
import json
import os
import stat
import time
import zipfile
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import (
    AnswerCallbackQuery,
    DeleteMessage,
    EditMessageText,
    SendDocument,
    SendMessage,
)
from aiogram.types import Chat, Document, InlineKeyboardMarkup, Message, ReplyKeyboardMarkup, Update
from telethon import errors

from telemirror import projects
from telemirror.misc.jsession import TDESKTOP_APP, save_jsession
from telemirror.panel import configstore, settings, turns
from telemirror.panel.app import build_dispatcher
from telemirror.panel.callbacks import ActCB, FltCB, NavCB
from telemirror.panel.configstore import ConfigStore
from telemirror.panel.middlewares import AdminOnly
from telemirror.panel.routers import accounts
from telemirror.panel.routers.maintenance import build_task_args
from telemirror.panel.runtime import Launch, Runtime
from telemirror.panel.safe_edit import SafeEdit
from telemirror.panel.systemd import Systemd
from tests._panel import ADMIN_ID, FakeSystemd, STRANGER_ID, _user, callback_update, make_bot, message_update
from tests.conftest import run

LIVE_YAML = """\
# live mirror — hand-written comment
disable_edit: true
filters:
  - SkipWithKeywordsFilter:
      keywords: !!set
        ? реклама
directions:
  - from: [-1001111111111]
    to: [-1002222222222]
"""
ME = SimpleNamespace(first_name="Тест", last_name=None, id=7, phone="79990000000", username="tester")
SESSION = "sessions/79990000000.jsession"


async def _ok(_project, _text):
    return None


_DP: list = []


def _dispatcher():
    # Routers are module singletons (attachable once) — one Dispatcher for the
    # module, fresh per-test state injected in the fixture.
    if not _DP:
        _DP.append(build_dispatcher(frozenset({ADMIN_ID})))
    return _DP[0]


class Env:
    bot: Any
    live: Any

    def feed(self, update):
        run(self.dp.feed_update(self.bot, update))
        # Telegram refuses a callback answer (toast / alert) over 200 characters.
        for answer in self.session.of(AnswerCallbackQuery):
            assert len(answer.text or "") <= 200, answer.text

    def sent(self):
        return [r for r in self.session.requests if isinstance(r, (SendMessage, EditMessageText))]

    def last_text(self) -> str:
        return str(self.sent()[-1].text)

    def last_kb(self) -> InlineKeyboardMarkup:
        for r in reversed(self.sent()):
            if isinstance(r.reply_markup, InlineKeyboardMarkup):
                return r.reply_markup
        raise AssertionError("no inline keyboard sent")

    def labels(self) -> list:
        return [b.text for row in self.last_kb().inline_keyboard for b in row]

    def press(self, label: str) -> str:
        """Tap the button of the last keyboard whose label starts with ``label``."""
        for row in self.last_kb().inline_keyboard:
            for b in row:
                if b.text.startswith(label):
                    assert b.callback_data is not None
                    self.feed(callback_update(b.callback_data))
                    return b.callback_data
        raise AssertionError(f"no button {label!r} in {self.labels()}")

    def type(self, text: str) -> None:
        self.feed(message_update(text))

    def upload(self, name: str, data: bytes) -> None:
        self.upload_album([(name, data)])

    def upload_album(self, files: list) -> None:
        """Documents sent together (one album when more than one), fed at once
        as Telegram delivers them: one update each."""
        by_id = {f"f{n}": data for n, (_, data) in enumerate(files)}

        async def fake_download(file, *a, **kw):
            return io.BytesIO(by_id[file.file_id])

        self.bot.download = fake_download
        group = "g1" if len(files) > 1 else None
        updates = [Update(update_id=int(time.time() * 1000) % 10**9 + n, message=Message(
            message_id=99_002 + n, date=datetime.now(), chat=Chat(id=ADMIN_ID, type="private"),
            from_user=_user(ADMIN_ID), media_group_id=group,
            document=Document(file_id=f"f{n}", file_unique_id=f"u{n}", file_name=name, file_size=len(data)),
        )) for n, (name, data) in enumerate(files)]

        async def feed_all():
            await asyncio.gather(*(self.dp.feed_update(self.bot, u) for u in updates))

        run(feed_all())

    def data(self, project=None) -> dict:
        return yaml.safe_load((project or self.live).config_path.read_text(encoding="utf-8"))


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(projects, "REPO_DIR", tmp_path)
    monkeypatch.setattr(projects, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(settings, "TASK_ENV_DIR", tmp_path / "run")
    save_jsession(str(tmp_path / SESSION), "1AAAA", ME, TDESKTOP_APP)
    live = projects.create_project("Зеркало", "🪞", SESSION)
    live.config_path.write_text(LIVE_YAML, encoding="utf-8")
    e = Env()
    e.fake = FakeSystemd({live.live_unit: "active"})
    e.dp = _dispatcher()
    e.dp["sysd"] = Systemd(runner=e.fake)
    e.dp["store"] = ConfigStore(validator=_ok)
    e.dp["runtime"] = Runtime()
    e.dp.fsm.storage = MemoryStorage()
    e.bot, e.session = make_bot()
    e.live, e.tmp = live, tmp_path
    return e


def _open_card(env, project=None):
    env.feed(callback_update(NavCB(s="card", p=(project or env.live).key).pack()))


# ── access, start, navigation ───────────────────────────────────────────────


def test_admin_only_requires_admins():
    with pytest.raises(ValueError):
        AdminOnly(frozenset())


def test_stranger_gets_nothing(env):
    env.feed(message_update("/start", uid=STRANGER_ID))
    env.feed(callback_update(NavCB(s="prj").pack(), uid=STRANGER_ID))
    env.feed(callback_update(ActCB(a="stop", p=env.live.key).pack(), uid=STRANGER_ID))
    assert env.session.requests == []
    assert env.fake.calls == []


def test_start_screen(env):
    env.type("/start")
    sent = env.session.of(SendMessage)
    assert len(sent) == 1
    text = sent[0].text
    assert "👋 Здравствуйте, <b>Даниил &lt;b&gt;</b>!" in text  # the name is HTML-escaped
    assert "📁 Проектов: <b>1</b> · 🟢 зеркал работает: <b>1</b>" in text
    for section in ("<b>📁 Проекты</b> —", "<b>📊 Задачи</b> —", "<b>⚙️ Настройки</b> —"):
        assert section in text
    assert text.endswith("<i>Выберите раздел в меню ниже 👇</i>")
    kb = sent[0].reply_markup
    assert isinstance(kb, ReplyKeyboardMarkup) and kb.resize_keyboard
    assert [b.text for b in kb.keyboard[0]] == ["📁 Проекты", "📊 Задачи", "⚙️ Настройки"]


def test_main_menu_sends_new_buttons_edit_in_place_and_every_tap_is_answered(env):
    env.type("📁 Проекты")
    assert isinstance(env.sent()[-1], SendMessage)
    assert env.labels()[0].startswith("➕ Новый проект")
    env.press("🪞 Зеркало")
    for label in ("🔀 Направления", "1. ", "🧹 Фильтры направления", "⬅️ Назад", "⬅️ Назад",
                  "⬅️ Назад", "🔧 Параметры", "⬅️ Назад", "⏪ Догрузка", "⬅️ Назад", "🛠 Обслуживание",
                  "📌 Закрепы", "⬅️ Назад", "⬅️ Назад", "🗂 Конфиг", "⬅️ Назад", "🧰 Управление",
                  "⬅️ Назад", "🧹 Фильтры", "⬅️ Назад", "⬅️ Назад"):
        env.press(label)
    edits = env.session.of(EditMessageText)
    assert len(env.session.of(SendMessage)) == 1
    assert all(e.message_id == 77 for e in edits)
    assert len(env.session.of(AnswerCallbackQuery)) == len(edits)
    assert "<b>📁 Проекты</b>" in edits[-1].text  # back at the list


def test_project_screens_carry_breadcrumbs_and_every_button_is_described(env):
    _open_card(env)
    card = env.last_text()
    assert "🪞 <b>Зеркало</b>" in card
    assert "<b>▶️ Запустить</b>" not in card and "<b>⏹ Остановить</b> —" in card  # it runs
    env.press("🔀 Направления")
    assert "🪞 <b>Зеркало</b> › <b>🔀 Направления</b>" in env.last_text()
    env.press("1. ")
    text = env.last_text()
    assert "🪞 <b>Зеркало</b> › <b>🔀 Направления</b> › <b>🔀 Направление</b>" in text
    for label in env.labels():
        if label.startswith(("⬅️", "🔄")) or label.endswith("›"):
            continue
        assert f"<b>{label}</b> —" in text, label
    assert env.labels()[-1] == "⬅️ Назад"


def test_stale_and_unknown_buttons_are_answered(env):
    env.feed(callback_update("garbage:data"))
    env.feed(callback_update(NavCB(s="card", p="gone").pack()))
    answers = env.session.of(AnswerCallbackQuery)
    assert answers[0].show_alert and "устарела" in answers[0].text
    env.type("hello")
    assert "Выберите раздел в меню ниже" in env.last_text()


def test_callback_data_fits_64_bytes():
    key = "x" * projects.KEY_MAX
    worst = [
        NavCB(s="dflt", p=key, i=10**6, pg=10**6),
        ActCB(a="acc_upload", p=key, i=10**6, pg=10**6, h="ffffffff"),
        FltCB(a="x", p=key, d=10**4, f=999, k=9, n=10**4, pg=10**4, h="ffffffff"),
    ]
    for cb in worst:
        packed = cb.pack()
        assert len(packed.encode()) <= 64, packed
        assert type(cb).unpack(packed) == cb


def test_safe_edit_swallows_not_modified_and_resends_the_uneditable():
    bot, session = make_bot()
    calls = []

    async def make_request(bot_, method, timeout=None):
        calls.append(method)
        if isinstance(method, EditMessageText):
            raise TelegramBadRequest(method=method, message=reason[0])
        return True

    async def through(bot_, method):
        return await SafeEdit()(make_request, bot_, method)

    edit = EditMessageText(text="x", chat_id=1, message_id=5)
    reason = ["Bad Request: message is not modified"]
    assert run(through(bot, edit)) is True
    reason[0] = "Bad Request: message to edit not found"
    run(through(bot, edit))
    assert isinstance(calls[-1], SendMessage) and calls[-1].text == "x"


def test_handler_crash_is_reported_to_the_admin(env, monkeypatch):
    from telemirror.panel.routers import tasks as tasks_router

    async def boom(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setitem(__import__("telemirror.panel.screens", fromlist=["VIEWS"]).VIEWS, "tsk", boom)
    env.feed(callback_update(NavCB(s="tsk").pack()))
    assert "Внутренняя ошибка панели" in env.session.of(SendMessage)[-1].text
    assert "RuntimeError" in env.session.of(SendMessage)[-1].text
    assert tasks_router  # imported for its view registration


# ── ➕ Новый проект ──────────────────────────────────────────────────────────


def test_new_project_name_icon_account(env):
    env.type("📁 Проекты")
    env.press("➕ Новый проект")
    env.type("Зеркало")  # taken
    assert "уже есть" in env.last_text()
    env.type("Новости")
    assert "значок" in env.last_text()
    env.type("abc")
    assert "Не подходит" in env.last_text()
    env.type("📁")  # a section's emoji
    assert "раздел бота" in env.last_text()
    env.press("🚀")
    assert "выберите аккаунт" in env.last_text()
    env.press("👤 +79990000000")
    created = projects.load_project("novosti")
    assert (created.name, created.icon, created.session) == ("Новости", "🚀", SESSION)
    assert env.data(created)["directions"] == []
    assert "✅ Проект 🚀 Новости создан" in env.last_text()
    assert "🔀 Направления → ➕ Добавить" in env.last_text()
    assert "работают по очереди" in env.last_text()  # it shares the session with «Зеркало»


def test_new_project_cancel_returns_to_the_list(env):
    env.type("📁 Проекты")
    env.press("➕ Новый проект")
    env.press("✖️ Отмена")
    assert env.last_text() == "Отменено."
    env.press("⬅️ Назад")
    assert "<b>📁 Проекты</b>" in env.last_text()
    assert len(projects.list_projects()) == 1


def test_cancel_command_leaves_a_form_with_a_way_back(env):
    env.type("📁 Проекты")
    env.press("➕ Новый проект")
    env.type("/cancel")
    assert env.last_text() == "Отменено."
    assert env.labels() == ["⬅️ Назад"]
    env.type("Не имя")  # out of the form: no project is made
    assert len(projects.list_projects()) == 1


def test_starting_an_empty_project_is_refused(env):
    empty = projects.create_project("Пусто", "🔥", SESSION)
    _open_card(env, empty)
    env.press("▶️ Запустить")
    answer = env.session.of(AnswerCallbackQuery)[-1]
    assert answer.show_alert and "нет направлений" in answer.text
    assert not any(c[2] in ("start", "enable") for c in env.fake.calls if c[0] == "systemctl" and len(c) > 2)


def test_a_mirror_on_a_shared_session_asks_then_replaces_the_other(env):
    other = projects.create_project("Курсы", "🎓", SESSION)
    other.config_path.write_text(LIVE_YAML, encoding="utf-8")
    _open_card(env, other)
    env.press("▶️ Запустить")
    assert "🪞 Зеркало · пересылка" in env.last_text() and "будет выключено" in env.last_text()
    env.press("✅ Да")
    # a mirror replaces the other for good: no resume, and not on the next boot either
    assert ["systemctl", "--no-block", "disable", "--now", env.live.live_unit] in env.fake.calls
    assert ["systemctl", "--no-block", "enable", "--now", other.live_unit] in env.fake.calls
    assert turns.load() == []


def test_a_restart_on_a_busy_session_turns_the_other_mirror_off(env):
    """👤 Аккаунт moved the project onto a session another running mirror holds:
    🔁 must hand the session over (as ▶️ does), not crash-loop on its lock."""
    other = projects.create_project("Курсы", "🎓", SESSION)
    other.config_path.write_text(LIVE_YAML, encoding="utf-8")
    env.fake.states[other.live_unit] = "active"
    for open_restart in (
        lambda: (_open_card(env), env.press("🔁 Перезапустить")),
        lambda: (env.feed(callback_update(NavCB(s="unit", p=env.live.key, i=0).pack())),
                 env.press("🔁 Перезапустить")),
    ):
        env.fake.calls.clear()
        env.dp["runtime"].last_start.clear()
        open_restart()
        assert "🎓 Курсы · пересылка" in env.last_text() and "будет выключено" in env.last_text()
        env.press("✅ Да")
        assert ["systemctl", "--no-block", "disable", "--now", other.live_unit] in env.fake.calls
        assert ["systemctl", "--no-block", "restart", env.live.live_unit] in env.fake.calls


def test_a_restart_alone_on_its_session_just_restarts(env):
    _open_card(env)
    env.press("🔁 Перезапустить")
    assert "будет выключено" not in env.last_text()
    env.press("✅ Да")
    controls = [c for c in env.fake.calls if c[:2] == ["systemctl", "--no-block"]]
    assert controls == [["systemctl", "--no-block", "restart", env.live.live_unit]]


def test_a_project_without_its_config_file_is_not_started(env):
    env.fake.states.clear()
    env.live.config_path.unlink()
    _open_card(env)
    env.press("▶️ Запустить")
    answer = env.session.of(AnswerCallbackQuery)[-1]
    assert answer.show_alert and "не найден" in answer.text
    assert not any("enable" in c for c in env.fake.calls)


def test_stop_needs_a_fresh_confirmation(env, monkeypatch):
    _open_card(env)
    env.press("⏹ Остановить")
    yes = env.press("✅ Да")
    assert ["systemctl", "--no-block", "disable", "--now", env.live.live_unit] in env.fake.calls
    env.fake.calls.clear()
    env.feed(callback_update(yes))  # the same «Да» again
    assert env.fake.calls == []
    assert env.session.of(AnswerCallbackQuery)[-1].show_alert

    _open_card(env)
    env.press("🔁 Перезапустить")
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + settings.CONFIRM_TTL_SEC + 1)
    env.press("✅ Да")
    assert "устарело" in env.session.of(AnswerCallbackQuery)[-1].text
    assert not any("restart" in c for c in env.fake.calls)


# ── 🧰 Управление ───────────────────────────────────────────────────────────


def test_rename_icon_and_delete_project(env):
    _open_card(env)
    env.press("🧰 Управление")
    env.press("🏷 Переименовать")
    env.type("Цитадель")
    assert projects.load_project(env.live.key).name == "Цитадель"
    env.press("🎨 Значок")
    env.press("🏰")
    assert projects.load_project(env.live.key).icon == "🏰"
    env.press("🗑 Удалить проект")
    assert "будут остановлены" in env.last_text()
    env.press("🗑 Да, удалить")
    assert projects.list_projects() == []
    assert ["systemctl", "--no-block", "disable", "--now", env.live.live_unit] in env.fake.calls
    assert "удалён" in env.last_text() and "projects/.deleted/" in env.last_text()
    archived = list((projects.PROJECTS_DIR / ".deleted").glob(f"{env.live.key}-*/mirror.config.yml"))
    assert len(archived) == 1  # undoable: move it back


def test_change_account(env):
    save_jsession(str(env.tmp / "sessions" / "79991112233.jsession"), "1BBBB",
                  SimpleNamespace(**{**vars(ME), "phone": "79991112233", "username": None}), TDESKTOP_APP)
    _open_card(env)
    env.press("🧰 Управление")
    env.press("👤 Аккаунт")
    env.press("👤 +79991112233")
    assert projects.load_project(env.live.key).session == "sessions/79991112233.jsession"
    assert "Перезапустите зеркало" in env.last_text()


# ── 🔀 Направления ──────────────────────────────────────────────────────────


def test_add_direction_flow(env):
    _open_card(env)
    env.press("🔀 Направления")
    env.press("➕ Добавить")
    env.type("not an id")
    assert "Неверный ID канала" in env.last_text()
    env.type("-1005555555555")
    env.type("-1006666666666#3, -1007777777777")
    env.press("↪️ Пересылка")
    env.press("📚 Всю историю")
    added = env.data()["directions"][-1]
    assert added == {"from": [-1005555555555], "to": ["-1006666666666#3", -1007777777777],
                     "mode": "forward", "past_mode": {"full_history": True}}
    assert "# live mirror — hand-written comment" in env.live.config_path.read_text(encoding="utf-8")
    assert "🔁 Перезапустить" in env.last_text()  # the mirror runs: the note says how to apply


def test_direction_toggles_values_and_delete(env):
    _open_card(env)
    env.press("🔀 Направления")
    env.press("1. ")
    assert "✏️ Правки: выкл" in env.labels()  # inherited disable_edit: true
    env.press("✏️ Правки")
    assert env.data()["directions"][0]["disable_edit"] is False
    env.press("↔️ Режим")
    assert env.data()["directions"][0]["mode"] == "forward"
    env.press("⏱ Задержка")
    env.type("abc")
    assert "Неверное число" in env.last_text()
    env.type("1.5")
    assert env.data()["directions"][0]["send_delay"] == 1.5
    env.press("📜 История")
    env.press("🔢 Последние N")
    env.type("100")
    assert env.data()["directions"][0]["past_mode"] == {"last_n": 100}
    env.press("🎯 Получатели")
    env.type("-1008888888888")
    assert env.data()["directions"][0]["to"] == [-1008888888888]
    env.press("🗑 Удалить")
    env.press("✖️ Отмена")
    assert len(env.data()["directions"]) == 1
    env.press("🗑 Удалить")
    env.press("🗑 Да, удалить")
    assert env.data()["directions"] == []
    assert configstore.backup_path(env.live).exists()


def test_navigating_away_leaves_the_input(env):
    _open_card(env)
    env.press("🔧 Параметры")
    env.press("🛰 Техканал")
    env.feed(callback_update(NavCB(s="tsk").pack()))  # e.g. a notification's button
    env.type("-1007777777777")  # out of the form: nothing is written
    assert "tech_channel" not in env.data()
    _open_card(env)
    env.press("🔧 Параметры")
    env.press("🛰 Техканал")
    env.type("-1007777777777")
    assert env.data()["tech_channel"] == -1007777777777
    env.press("🛰 Техканал")
    env.type("-")
    assert "tech_channel" not in env.data()


def test_params_toggles(env):
    _open_card(env)
    env.press("🔧 Параметры")
    assert "✏️ Правки: выкл" in env.labels()
    env.press("✏️ Правки")
    assert env.data()["disable_edit"] is False
    env.press("↔️ Режим")
    assert env.data()["mode"] == "forward"


def test_filter_editor_add_and_remove(env):
    _open_card(env)
    env.press("🧹 Фильтры")
    env.press("✏️ 1. SkipWithKeywordsFilter")
    assert "реклама" in env.last_text()
    env.press("➕ Добавить")
    env.type("спам\nказино")
    assert set(env.data()["filters"][0]["SkipWithKeywordsFilter"]["keywords"]) == {"реклама", "спам", "казино"}
    env.press("✖️ 1. казино")
    assert set(env.data()["filters"][0]["SkipWithKeywordsFilter"]["keywords"]) == {"реклама", "спам"}


def test_add_filters_with_and_without_a_required_value(env):
    _open_card(env)
    env.press("🧹 Фильтры")
    env.press("➕ Добавить фильтр")
    env.press("SkipUrlFilter")
    assert [projects_filter_name(f) for f in env.data()["filters"]] == ["SkipWithKeywordsFilter", "SkipUrlFilter"]
    env.press("➕ Добавить фильтр")
    env.press("KeywordReplaceFilter")
    assert "что =&gt; на что" in env.last_text()
    env.type("реклама => промо")
    assert env.data()["filters"][-1] == {"KeywordReplaceFilter": {"keywords": {"реклама": "промо"}}}


def projects_filter_name(entry) -> str:
    return configstore.filter_name(entry)


def test_filter_card_toggles_moves_and_deletes(env):
    _open_card(env)
    env.press("🧹 Фильтры")
    env.press("➕ Добавить фильтр")
    env.press("SkipUrlFilter")
    env.press("✏️ 2. SkipUrlFilter")
    env.press("☑️ и с @упоминаниями")
    assert env.data()["filters"][1] == {"SkipUrlFilter": {"skip_mention": False}}
    assert "⬜ и с @упоминаниями" in env.labels()
    env.press("⬆️ Выше")
    assert [projects_filter_name(f) for f in env.data()["filters"]] == ["SkipUrlFilter", "SkipWithKeywordsFilter"]
    env.press("🗑 Удалить фильтр")
    env.press("🗑 Да, удалить")
    assert [projects_filter_name(f) for f in env.data()["filters"]] == ["SkipWithKeywordsFilter"]


def test_mention_names_and_watermark_args(env):
    _open_card(env)
    env.press("🧹 Фильтры")
    env.press("➕ Добавить фильтр")
    env.press("UrlMessageFilter")
    env.press("✏️ 2. UrlMessageFilter")
    env.press("📝 только эти @…")
    assert "с <code>@</code>" in env.last_text()
    env.type("@spam\n@ads")
    assert env.data()["filters"][1] == {"UrlMessageFilter": {"filter_mention": {"@spam", "@ads"}}}
    env.press("✖️ 1. @ads")
    env.press("✖️ 1. @spam")
    assert env.data()["filters"][1] == {"UrlMessageFilter": {}}
    assert "⬜ убирать @упоминания" in env.labels()  # a bool again
    env.press("⬅️ Назад")
    env.press("➕ Добавить фильтр")
    env.press("WatermarkRemovalFilter")
    env.press("✏️ 3. WatermarkRemovalFilter")
    assert "свой знак: прозрачность: по умолчанию (0.55)" in env.last_text()
    env.press("📝 свой знак: прозрачность")
    env.type("0,4")
    assert env.data()["filters"][2] == {"WatermarkRemovalFilter": {"stamp_opacity": 0.4}}


def test_a_directions_first_own_filter_keeps_the_projects(env):
    _open_card(env)
    env.press("🔀 Направления")
    env.press("1. ")
    env.press("🧹 Фильтры направления")
    env.press("➕ Добавить фильтр")
    env.press("SkipAllFilter")
    own = [projects_filter_name(f) for f in env.data()["directions"][0]["filters"]]
    assert own == ["SkipWithKeywordsFilter", "SkipAllFilter"]
    assert "скопированы" in env.last_text()


def test_a_directions_link_and_the_replays_pause(env):
    cfg = env.data()
    cfg["directions"][0]["past_mode"] = {"full_history": True}
    env.live.config_path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    _open_card(env)
    env.press("🔀 Направления")
    env.press("1. ")
    assert "🔗 Ссылка-замена: общая" in env.labels()
    env.press("🔗 Ссылка-замена")
    env.type("https://t.me/x")
    assert env.data()["directions"][0]["fallback_link_url"] == "https://t.me/x"
    _open_card(env)
    env.press("⏪ Догрузка")
    assert "⏱ Задержка: 0.5 с" in env.labels()
    env.press("⏱ Задержка")
    env.type("2")
    assert env.data()["directions"][0]["past_mode"] == {"full_history": True, "send_delay": 2}


def test_one_directions_replay_delay(env):
    _open_card(env)
    env.press("🔀 Направления")
    env.press("1. ")
    assert not any(b.startswith("⏱ Задержка догрузки") for b in env.labels())  # no history yet
    env.press("📜 История")
    env.press("📚 Всю")
    assert "⏱ Задержка догрузки: по умолч. (0.5 с)" in env.labels()
    env.press("⏱ Задержка догрузки")
    env.type("3")
    assert env.data()["directions"][0]["past_mode"] == {"full_history": True, "send_delay": 3}
    assert "⏱ Задержка догрузки: 3.0 с" in env.labels()
    env.press("⏱ Задержка догрузки")
    env.type("-")
    assert env.data()["directions"][0]["past_mode"] == {"full_history": True}


# ── ⏪ Догрузка, 🛠 Обслуживание, 📊 Задачи ───────────────────────────────────


def test_replay_needs_history_then_pauses_the_mirror(env):
    _open_card(env)
    env.press("⏪ Догрузка")
    env.press("▶️ Начать")
    assert "не задана история" in env.session.of(AnswerCallbackQuery)[-1].text
    cfg = env.data()
    cfg["directions"][0]["past_mode"] = {"full_history": True}
    env.live.config_path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    env.press("🔄 Обновить")
    env.press("▶️ Начать")
    assert "будет остановлено" in env.last_text()
    env.press("✅ Да")
    assert ["systemctl", "--no-block", "start", env.live.past_unit] in env.fake.calls
    assert turns.load()[0]["resume"] == [env.live.live_unit]


def test_maintenance_dry_run_writes_the_task_env_file(env):
    _open_card(env)
    env.press("🛠 Обслуживание")
    env.press("📌 Закрепы")
    env.press("⬜ Только добавлять")
    assert "☑️ Только добавлять" in " ".join(env.labels())
    assert not any(label.startswith("▶️ Выполнить") for label in env.labels())  # no dry run yet
    env.press("🔍 Проверить")
    env.press("✅ Да")
    env_file = (env.tmp / "run" / f"{env.live.key}.env").read_text()
    assert env_file == "TASK_MODULE=sync_pins\nTASK_ARGS=--additive --dry-run\n"
    assert ["systemctl", "--no-block", "start", env.live.task_unit] in env.fake.calls


@pytest.mark.parametrize("screen, module", [("🕶 Анонимность", "anonymize_groups"),
                                            ("🧨 Очистка каналов", "clear_channels")])
def test_maintenance_scripts_without_flags(env, screen, module):
    _open_card(env)
    env.press("🛠 Обслуживание")
    env.press(screen)
    assert not any(label.startswith("▶️ Выполнить") for label in env.labels())  # no dry run yet
    env.press("🔍 Проверить")
    env.press("✅ Да")
    env_file = (env.tmp / "run" / f"{env.live.key}.env").read_text()
    assert env_file == f"TASK_MODULE={module}\nTASK_ARGS=--dry-run\n"
    assert ["systemctl", "--no-block", "start", env.live.task_unit] in env.fake.calls


def test_clearing_for_real_asks_with_the_delete_button(env):
    """🧨 Очистка каналов is irreversible: after a successful check the real run
    is confirmed with 🗑 Да, удалить, not the usual ✅ Да."""
    from telemirror.panel.routers.maintenance import config_sha

    env.dp["runtime"].launches[(env.live.key, "cc")] = Launch(("--dry-run",), True, 0.0, config_sha(env.live))
    _open_card(env)
    env.press("🛠 Обслуживание")
    env.press("🧨 Очистка каналов")
    env.press("▶️ Выполнить")
    assert "будут удалены" in env.last_text()
    assert env.labels() == ["🗑 Да, удалить", "✖️ Отмена"]
    env.press("🗑 Да, удалить")
    env_file = (env.tmp / "run" / f"{env.live.key}.env").read_text()
    assert env_file == "TASK_MODULE=clear_channels\nTASK_ARGS=--yes\n"


def test_a_real_run_needs_its_own_check_to_be_the_last_run(env):
    """The task unit is shared by every task of a project: another task's later
    success must not unlock ▶️ Выполнить of one whose own check failed."""
    from telemirror.panel.routers.maintenance import can_run_real, config_sha
    from telemirror.panel.systemd import parse_show
    from tests._panel import SHOW

    runtime = env.dp["runtime"]
    st = parse_show(SHOW.format(active="inactive", sub="dead", result="success"))  # ended at 1763390000
    sha = config_sha(env.live)
    runtime.launches[(env.live.key, "cc")] = Launch(("--dry-run",), True, 1_600_000_000.0, sha)  # failed
    runtime.launches[(env.live.key, "rs")] = Launch(("--dry-run",), True, 1_650_000_000.0, sha)  # succeeded
    assert can_run_real("rs", env.live, runtime, st)
    assert not can_run_real("cc", env.live, runtime, st)


def test_a_real_run_needs_a_check_of_the_current_config(env):
    """A recipient added after the check was never in the plan it showed:
    🧨 Очистка must not delete there without a new check."""
    from telemirror.panel.routers.maintenance import can_run_real, config_sha
    from telemirror.panel.systemd import parse_show
    from tests._panel import SHOW

    runtime = env.dp["runtime"]
    st = parse_show(SHOW.format(active="inactive", sub="dead", result="success"))
    runtime.launches[(env.live.key, "cc")] = Launch(("--dry-run",), True, 1_600_000_000.0, config_sha(env.live))
    assert can_run_real("cc", env.live, runtime, st)
    env.live.config_path.write_text(LIVE_YAML + "# a recipient added since\n", encoding="utf-8")
    assert not can_run_real("cc", env.live, runtime, st)


def test_a_confirmed_run_is_checked_again(env):
    """Between the question and «Да» the task unit may have started (another
    admin, another screen): «Да» then starts nothing."""
    _open_card(env)
    env.press("🛠 Обслуживание")
    env.press("🕶 Анонимность")
    env.press("🔍 Проверить")
    env.fake.states[env.live.task_unit] = "active"
    env.press("✅ Да")
    assert ["systemctl", "--no-block", "start", env.live.task_unit] not in env.fake.calls
    assert not (env.tmp / "run" / f"{env.live.key}.env").exists()


def test_build_task_args_for_the_maintenance_scripts():
    assert build_task_args("ag", True) == ["--dry-run"]
    assert build_task_args("cc", False) == ["--yes"]
    with pytest.raises(ValueError):
        build_task_args("cc", False, frozenset({"--additive"}))


def test_pins_limit_and_donors_reach_the_task(env):
    _open_card(env)
    env.press("🛠 Обслуживание")
    env.press("📌 Закрепы")
    env.press("📏 Лимит")
    env.type("50")
    env.press("📍 Доноры")
    env.type("-1009999999999")
    assert "не источники проекта" in env.last_text()
    env.type("-1001111111111")
    assert "📍 Доноры: 1" in " ".join(env.labels())
    env.press("🔍 Проверить")
    env.press("✅ Да")
    env_file = (env.tmp / "run" / f"{env.live.key}.env").read_text()
    assert env_file == "TASK_MODULE=sync_pins\nTASK_ARGS=--max-pins 50 --only -1001111111111 --dry-run\n"


def test_build_task_args_refuses_bad_pin_options():
    assert build_task_args("sp", True, frozenset(), {"max_pins": 5, "only": (-1001111111111,)}) == [
        "--max-pins", "5", "--only", "-1001111111111", "--dry-run"]
    for opts in ({"max_pins": 0}, {"max_pins": "5; rm"}, {"only": ("-100 1",)}, {"only": (5,)}):
        with pytest.raises(ValueError):
            build_task_args("sp", True, frozenset(), opts)
    with pytest.raises(ValueError):
        build_task_args("rs", True, frozenset(), {"max_pins": 5})


def test_monitoring_timers_switch_on_and_off(env):
    env.type("⚙️ Настройки")
    assert "🩺 Проверка здоровья: выключена" in env.labels()
    env.press("🩺 Проверка здоровья")
    env.press("✅ Да")
    assert ["systemctl", "--no-block", "enable", "--now", "telemirror-health.timer"] in env.fake.calls
    env.fake.states["telemirror-restart.timer"] = "active"
    env.press("🔄 Обновить")
    env.press("🔁 Перезапуск по расписанию")
    assert "только после" in env.last_text()
    env.press("✅ Да")
    assert ["systemctl", "--no-block", "disable", "--now", "telemirror-restart.timer"] in env.fake.calls


def test_access_check_shows_its_report_and_runs_without_a_real_run(env):
    report = {"at": time.time(), "chats": [
        {"id": -1001111111111, "roles": ["source"], "title": "Донор", "ok": True, "reason": "", "note": "noforwards"},
        {"id": -1002222222222, "roles": ["target"], "title": "Зеркало <x>", "ok": False, "reason": "cannot_post",
         "note": ""},
    ]}
    projects.access_report_path(env.live.key).write_text(json.dumps(report), encoding="utf-8")
    _open_card(env)
    env.press("🛠 Обслуживание")
    env.press("🛂 Доступ")
    text = env.last_text()
    assert "✅ 1 · ❌ 1" in text and "Зеркало &lt;x&gt;" in text and "нет права публиковать" in text
    assert "запрет копирования" in text
    assert not any(label.startswith("▶️ Выполнить") for label in env.labels())
    env.press("🔍 Проверить")
    env.press("✅ Да")
    env_file = (env.tmp / "run" / f"{env.live.key}.env").read_text()
    assert env_file == "TASK_MODULE=check_access\nTASK_ARGS=\n"


def test_tasks_and_unit_card(env):
    env.type("📊 Задачи")
    assert "🪞 Зеркало · пересылка — 🟢 работает" in env.last_text()
    env.press("🪞 Зеркало · пересылка")
    text = env.last_text()
    assert "line &lt;two&gt;" in text  # the journal is escaped
    assert env.labels()[:2] == ["⏹ Остановить", "🔁 Перезапустить"]


# ── 🗂 Конфиг ───────────────────────────────────────────────────────────────


def test_download_upload_and_rollback(env):
    _open_card(env)
    env.press("🗂 Конфиг")
    env.press("📥 Скачать")
    assert env.session.of(SendDocument)[-1].document.data == LIVE_YAML.encode()
    new = "directions:\n  - from: [-1005555555555]\n    to: [-1006666666666]\n"
    env.press("📤 Загрузить")
    env.upload("mirror.config.yml", new.encode())
    assert "Что изменится" in env.last_text()
    assert env.live.config_path.read_text(encoding="utf-8") == LIVE_YAML
    env.press("✅ Да")
    assert env.live.config_path.read_text(encoding="utf-8") == new
    assert "Конфигурация заменена" in env.last_text()
    env.press("↩️ Откатить")
    env.press("✅ Да")
    assert env.live.config_path.read_text(encoding="utf-8") == LIVE_YAML


def test_a_broken_file_can_still_be_rolled_back(env):
    _open_card(env)
    env.press("🔧 Параметры")
    env.press("↔️ Режим")  # creates a good .bak
    env.live.config_path.write_text("directions: [unclosed\n", encoding="utf-8")
    _open_card(env)
    assert "Не удалось прочитать конфиг" in env.last_text()
    env.press("🗂 Конфиг")
    env.press("↩️ Откатить")
    env.press("✅ Да")
    assert yaml.safe_load(env.live.config_path.read_text(encoding="utf-8"))["directions"]


# ── 👤 Аккаунты ─────────────────────────────────────────────────────────────


@pytest.fixture
def importing(monkeypatch):
    """📤 Загрузить сессию with Telethon scripted (tests/test_session_import.py's
    client) and a short album wait."""
    from telemirror.misc import session_import
    from telemirror.panel.middlewares import AlbumMiddleware
    from tests.test_session_import import FakeClient as ImportClient

    monkeypatch.setattr(AlbumMiddleware, "LATENCY", 0.05)
    ImportClient.instances = []
    monkeypatch.setattr(session_import, "build_telegram_client", ImportClient)
    return ImportClient


def _zip(entries: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buf.getvalue()


def test_upload_a_session_file(env, importing):
    """A .jsession is checked like the other formats: connected, the account
    read from Telegram (not the file's claims), its app kept."""
    env.type("⚙️ Настройки")
    env.press("👤 Аккаунты")
    env.press("📤 Загрузить сессию")
    env.upload("x.jsession", b"not json")
    assert "это не .jsession" in env.last_text()
    env.upload("x.jsession", b"[]")  # JSON, but not a .jsession
    assert "это не .jsession" in env.last_text()
    assert importing.instances == []  # nothing connected for a broken file
    data = {"auth_key": "1CCCC", "account": {"phone_number": "70000000000"},
            "application": {"api_id": 2040, "api_hash": "h", "device_name": "PC"}}
    env.upload("x.jsession", json.dumps(data).encode())
    assert len(importing.instances) == 1
    saved = env.tmp / "sessions" / "79990001122.jsession"
    written = json.loads(saved.read_text())
    assert written["auth_key"] == "1CCCC" and written["application"]["device_name"] == "PC"
    assert stat.S_IMODE(os.stat(saved).st_mode) == 0o600
    assert any(isinstance(r, DeleteMessage) for r in env.session.requests)  # the file left the chat
    assert "✅ Сессия +79990001122 · @imp сохранена" in env.last_text()


def test_an_unauthorized_jsession_is_not_saved(env, importing, monkeypatch):
    monkeypatch.setattr(importing, "AUTHORIZED", False)
    env.type("⚙️ Настройки")
    env.press("👤 Аккаунты")
    env.press("📤 Загрузить сессию")
    data = {"auth_key": "1CCCC", "application": {"api_id": 2040, "api_hash": "h"}}
    env.upload("x.jsession", json.dumps(data).encode())
    assert "не авторизована" in env.last_text()
    assert not (env.tmp / "sessions" / "79990001122.jsession").exists()


def test_upload_a_session_with_its_json_as_an_album(env, importing):
    from tests.test_session_import import _session_file

    _session_file(env.tmp / "s.session")
    env.type("⚙️ Настройки")
    env.press("👤 Аккаунты")
    env.press("📤 Загрузить сессию")
    assert "tdata" in env.last_text() and ".session" in env.last_text()
    env.upload_album([("s.session", (env.tmp / "s.session").read_bytes()),
                      ("s.json", json.dumps({"app_id": 4, "app_hash": "h4", "device": "Pixel 7"}).encode())])
    saved = env.tmp / "sessions" / "79990001122.jsession"
    assert json.loads(saved.read_text())["application"]["device_name"] == "Pixel 7"
    assert len(importing.instances) == 1  # the album is one import
    assert sum(isinstance(r, DeleteMessage) for r in env.session.requests) == 2  # both files left the chat
    assert "✅ Сессия +79990001122 · @imp сохранена" in env.last_text()


def test_upload_a_tdata_asks_its_passcode(env, importing, monkeypatch):
    from telethon.crypto import AuthKey
    from telethon.sessions import StringSession

    from telemirror.misc import session_import

    key = StringSession()
    key.set_dc(2, "149.154.167.51", 443)
    key.auth_key = AuthKey(bytes(range(256)))

    async def read_tdata_key(tdata_dir, passcode=None):  # the child process, scripted
        assert tdata_dir.endswith("tdata")
        if passcode != "secret":
            raise session_import.NeedPasscode("неверный код-пароль" if passcode else "tdata защищена код-паролем")
        return key.save()

    monkeypatch.setattr(session_import, "read_tdata_key", read_tdata_key)
    env.type("⚙️ Настройки")
    env.press("👤 Аккаунты")
    env.press("📤 Загрузить сессию")
    env.upload("Telegram.zip", _zip({"Telegram/tdata/key_datas": b"x"}))
    assert "защищена код-паролем" in env.last_text()
    env.type("wrong")
    assert "неверный код-пароль" in env.last_text()
    env.type("secret")
    data = json.loads((env.tmp / "sessions" / "79990001122.jsession").read_text())
    assert data["application"] == TDESKTOP_APP
    assert sum(isinstance(r, DeleteMessage) for r in env.session.requests) == 3  # the ZIP and both passcodes


def test_upload_refusals(env, importing):
    env.type("⚙️ Настройки")
    env.press("👤 Аккаунты")
    env.press("📤 Загрузить сессию")
    env.upload("notes.txt", b"hi")
    assert "Не принято: notes.txt" in env.last_text()
    env.upload("empty.zip", _zip({"readme.md": b"x"}))
    assert "Не загружено: не найдено ни папки tdata, ни файла .session" in env.last_text()
    env.upload("x.session", b"not sqlite")  # still at the file step
    assert "файл .session не читается" in env.last_text()
    assert importing.instances == []  # nothing ever connected


class FakeClient:
    """Telethon's sign-in side, scripted."""

    def __init__(self, password=False):
        self.password = password
        self.session = SimpleNamespace(save=lambda: "1NEWSESSION")
        self.disconnected = False
        self.codes_sent = 0

    async def connect(self):
        pass

    async def send_code_request(self, phone):
        self.codes_sent += 1
        return SimpleNamespace(phone_code_hash=f"hash{self.codes_sent}")

    async def sign_in(self, phone=None, code=None, *, phone_code_hash=None, password=None):
        if password is None and code == "00000":
            raise errors.PhoneCodeExpiredError(None)
        if password is None and (code != "12345" or phone_code_hash != f"hash{self.codes_sent}"):
            raise errors.PhoneCodeInvalidError(None)
        if password is None and self.password:
            raise errors.SessionPasswordNeededError(None)
        if password is not None and password != "secret":
            raise errors.PasswordHashInvalidError(None)

    async def get_me(self):
        return SimpleNamespace(first_name="Новый", last_name=None, id=9, phone="79994443322", username="new")

    async def disconnect(self):
        self.disconnected = True


def test_login_by_phone_with_2fa_straight_into_a_new_project(env, monkeypatch):
    client = FakeClient(password=True)
    monkeypatch.setattr(accounts, "make_client", lambda: client)
    env.type("📁 Проекты")
    env.press("➕ Новый проект")
    env.type("Вход")
    env.press("🦊")
    env.press("🔑 Войти по номеру")
    env.type("12")
    assert "Не похоже на номер" in env.last_text()
    env.type("+7 999 444-33-22")
    env.type("1 1 1 1 1")
    assert "Неверный код" in env.last_text()
    env.type("1 2 3 4 5")
    assert "2FA" in env.last_text()
    env.type("wrong")
    env.type("secret")
    session = env.tmp / "sessions" / "79994443322.jsession"
    assert json.loads(session.read_text())["auth_key"] == "1NEWSESSION"
    assert json.loads(session.read_text())["password"] is None  # never stored
    assert client.disconnected
    project = projects.load_project("vhod")
    assert project.session == "sessions/79994443322.jsession"
    deleted = [r for r in env.session.requests if isinstance(r, DeleteMessage)]
    assert len(deleted) == 4  # two codes, two passwords
    assert "✅ Вход выполнен" in env.last_text() and "создан" in env.last_text()


def test_an_account_in_use_cannot_be_deleted(env):
    spare = env.tmp / "sessions" / "79991112233.jsession"
    save_jsession(str(spare), "1BBBB", SimpleNamespace(**{**vars(ME), "phone": "79991112233"}), TDESKTOP_APP)
    env.type("⚙️ Настройки")
    env.press("👤 Аккаунты")
    env.press("👤 +79990000000")
    assert "🪞 Зеркало" in env.last_text()
    assert not any(label.startswith("🗑") for label in env.labels())
    env.press("⬅️ Назад")
    env.press("👤 +79991112233")
    env.press("🗑 Удалить")
    env.press("🗑 Да, удалить")
    assert not spare.exists()


def test_an_expired_code_can_be_sent_again(env, monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(accounts, "make_client", lambda: client)
    env.type("⚙️ Настройки")
    env.press("👤 Аккаунты")
    env.press("🔑 Войти по номеру")
    env.type("+79994443322")
    env.type("0 0 0 0 0")
    assert "Код истёк" in env.last_text()
    env.press("📲 Отправить код заново")
    assert client.codes_sent == 2 and "Новый код отправлен" in env.last_text()
    env.type("1 2 3 4 5")  # checked against the new code's hash
    assert (env.tmp / "sessions" / "79994443322.jsession").exists()
    assert "✅ Вход выполнен" in env.last_text()


def test_a_project_whose_session_is_gone_says_where_to_fix_it(env):
    (env.tmp / SESSION).unlink()
    _open_card(env)
    assert "Файл сессии проекта не найден" in env.last_text()
    env.press("🔁 Перезапустить")  # a restart needs no session check: only start / runs do
    env.press("✖️ Отмена")
    env.press("🔧 Параметры")
    env.press("↔️ Режим")
    assert "🧰 Управление → 👤 Аккаунт" in env.last_text()
    assert "mode" not in env.data()  # nothing written
    env.press("⬅️ Назад")  # the refusal's ⬅️: back to 🔧 Параметры
    env.press("⬅️ Назад")
    env.press("⏪ Догрузка")
    env.press("▶️ Начать")
    answer = env.session.of(AnswerCallbackQuery)[-1]
    assert answer.show_alert and "сессии проекта не найден" in answer.text
