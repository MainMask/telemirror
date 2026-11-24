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
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import (
    AnswerCallbackQuery,
    DeleteMessage,
    EditMessageReplyMarkup,
    EditMessageText,
    SendDocument,
    SendMessage,
)
from aiogram.types import (
    Chat,
    ChatShared,
    Document,
    InlineKeyboardMarkup,
    Message,
    MessageOriginChannel,
    MessageOriginUser,
    ReplyKeyboardMarkup,
    Update,
)
from telethon import errors

from bot import configedit, configstore, pending, settings, texts, turns
from bot.app import build_dispatcher
from bot.callbacks import ActCB, FltCB, NavCB
from bot.configstore import ConfigStore
from bot.middlewares import AdminOnly, AlbumMiddleware
from bot.routers import accounts
from bot.routers.maintenance import build_task_args
from bot.runtime import Launch, Runtime
from bot.safe_edit import SafeEdit
from bot.states import PanelStorage
from bot.systemd import Systemd
from telemirror import projects, selfcheck, stats
from telemirror.misc.jsession import TDESKTOP_APP, save_jsession
from tests._panel import (
    ADMIN_ID,
    STRANGER_ID,
    FakeSystemd,
    _user,
    callback_update,
    make_bot,
    message_update,
)
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
    e.dp.fsm.storage = PanelStorage()
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
    for section in ("<b>📁 Проекты</b> —", "<b>📊 Статус</b> —", "<b>⚙️ Настройки</b> —"):
        assert section in text
    assert text.endswith("<i>Выберите раздел в меню ниже 👇</i>")
    kb = sent[0].reply_markup
    assert isinstance(kb, ReplyKeyboardMarkup) and kb.resize_keyboard
    assert [[b.text for b in row] for row in kb.keyboard] == [["📁 Проекты", "📊 Статус", "⚙️ Настройки"]]


def test_main_menu_sends_new_buttons_edit_in_place_and_every_tap_is_answered(env):
    env.type("📁 Проекты")
    assert isinstance(env.sent()[-1], SendMessage)
    assert env.labels()[0].startswith("➕ Новый проект")
    env.press("🪞 Зеркало")
    for label in ("🔀 Направления", "1. ", "🧹 Фильтры направления", "⬅️ Назад", "⬅️ Назад", "📢 Рассылка",
                  "⬅️ Назад", "⬅️ Назад", "⏪ Старые посты", "⬅️ Назад",
                  "🛠 Инструменты", "🛂 Проверка доступа", "⬅️ Назад", "📌 Закрепы", "⬅️ Назад", "⬅️ Назад",
                  "⚙️ Настройки проекта", "💾 Файл настроек", "⬅️ Назад", "⬅️ Назад", "🧹 Фильтры",
                  "⬅️ Назад", "⬅️ Назад"):
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


def _styles(env) -> dict:
    return {b.text: b.style for row in env.last_kb().inline_keyboard for b in row}


def test_colours_and_folded_details(env):
    env.fake.states[env.live.live_unit] = "inactive"
    _open_card(env)
    assert _styles(env)["▶️ Запустить"] == "primary"  # stopped and ready: the step to take now
    env.press("▶️ Запустить")
    env.press("⚙️ Настройки проекта")
    assert _styles(env)["🗑 Удалить проект"] == "danger"
    assert "<i>Копирование</i>\n<b>✏️ Повторять правки" in env.last_text()  # a group under its subheading
    assert "<blockquote expandable>" in env.last_text()  # how it works: folded
    env.press("🗑 Удалить проект")
    assert _styles(env) == {"🗑 Да, удалить": "danger", "✖️ Отмена": None}


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


def test_a_tap_answered_too_late_is_not_an_error():
    """Taps queued while the panel was down are answered at its start —
    Telegram refuses that answer; the tap itself is still handled."""
    bot, _ = make_bot()

    async def make_request(bot_, method, timeout=None):
        raise TelegramBadRequest(method=method, message=reason[0])

    async def through(method):
        return await SafeEdit()(make_request, bot, method)

    answer = AnswerCallbackQuery(callback_query_id="1")
    reason = ["Bad Request: query is too old and response timeout expired or query ID is invalid"]
    assert run(through(answer)) is True
    reason[0] = "Bad Request: something else"
    with pytest.raises(TelegramBadRequest):
        run(through(answer))


def test_handler_crash_is_reported_to_the_admin(env, monkeypatch):
    from bot.routers import tasks as tasks_router

    async def boom(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setitem(__import__("bot.screens", fromlist=["VIEWS"]).VIEWS, "tsk", boom)
    env.feed(callback_update(NavCB(s="tsk").pack()))
    assert "Что-то пошло не так" in env.session.of(SendMessage)[-1].text
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
    assert "от имени какого аккаунта работать?" in env.last_text()
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
    assert env.last_text().startswith("Отменено.")  # straight back, no extra ⬅️ tap
    assert "<b>📁 Проекты</b>" in env.last_text()
    assert isinstance(env.sent()[-1], EditMessageText)  # in the prompt's place
    assert len(projects.list_projects()) == 1


def test_cancel_command_goes_back_to_where_the_form_began(env):
    env.type("📁 Проекты")
    env.press("➕ Новый проект")
    env.type("/cancel")
    assert env.last_text().startswith("Отменено.")
    assert "<b>📁 Проекты</b>" in env.last_text()
    assert "➕ Новый проект" in env.labels()
    env.type("Не имя")  # out of the form: no project is made
    assert len(projects.list_projects()) == 1


def test_cancel_with_nothing_to_cancel_says_where_runs_are_stopped(env):
    env.type("/cancel")
    assert "Сейчас нечего отменять" in env.last_text()
    assert "на их экране в проекте" in env.last_text()


def test_an_answered_prompt_loses_its_buttons(env):
    def dropped():
        return [r for r in env.session.of(EditMessageReplyMarkup) if r.reply_markup is None]

    env.type("📁 Проекты")
    env.press("➕ Новый проект")
    env.type("x" * (settings.PROJECT_NAME_MAX + 1))  # refused: the same step, its ✖️ Отмена stays
    assert dropped() == []
    env.type("Новости")  # the next step's prompt: the name's one is spent
    assert len(dropped()) == 1
    assert "✖️ Отмена" in env.labels()  # the new prompt has its own


def test_a_finished_form_leaves_one_live_screen(env):
    _open_card(env)
    env.press("⚙️ Настройки проекта")  # the screen: message 77 (tests' callbacks)
    env.press("🏷 Переименовать")
    env.type("Новое имя")
    dropped = {r.message_id for r in env.session.of(EditMessageReplyMarkup) if r.reply_markup is None}
    assert 77 in dropped and len(dropped) == 2  # the screen above and the prompt; the outcome below is live
    assert "✅ Проект переименован" in env.last_text()


def test_button_hints_are_folded_under_the_screen(env):
    _open_card(env)
    env.press("⚙️ Настройки проекта")
    assert "<blockquote expandable><i>Копирование</i>\n<b>✏️ Повторять правки" in env.last_text()


def test_a_long_label_is_cut_with_an_ellipsis():
    assert texts.cut("короткий", 10) == "короткий"
    assert texts.cut("очень длинная подпись", 10) == "очень дли…"


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
    assert "🪞 Зеркало · зеркало" in env.last_text() and "будет выключено" in env.last_text()
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
    _open_card(env)
    env.press("🔁 Перезапустить")
    assert "🎓 Курсы · зеркало" in env.last_text() and "будет выключено" in env.last_text()
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


# ── ⚙️ Настройки проекта ────────────────────────────────────────────────────


def test_rename_icon_and_delete_project(env):
    _open_card(env)
    env.press("⚙️ Настройки проекта")
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
    env.press("⚙️ Настройки проекта")
    env.press("👤 Аккаунт")
    env.press("👤 +79991112233")
    assert projects.load_project(env.live.key).session == "sessions/79991112233.jsession"
    assert "Перезапустите зеркало" in env.last_text()


# ── 🔀 Направления ──────────────────────────────────────────────────────────


def forwarded_update(chat_id: int, title: str) -> Update:
    """A post the admin forwards from a channel."""
    return Update(update_id=int(time.time() * 1000) % 10**9, message=Message(
        message_id=99_500, date=datetime.now(), chat=Chat(id=ADMIN_ID, type="private"),
        from_user=_user(ADMIN_ID), text="пост из канала",
        forward_origin=MessageOriginChannel(date=datetime.now(), message_id=5,
                                            chat=Chat(id=chat_id, type="channel", title=title)),
    ))


def test_add_direction_flow(env):
    _open_card(env)
    env.press("🔀 Направления")
    env.press("➕ Добавить")
    env.type("not an id")
    assert "Не похоже на канал" in env.last_text()
    env.type("-1005555555555")
    env.type("-1006666666666#3, -1007777777777")
    env.press("✅ Готово")
    assert "шаг 3 из 3" in env.last_text()  # no mode step: the project's mode
    env.press("📚 Вся история")
    added = env.data()["directions"][-1]
    assert added == {"from": [-1005555555555], "to": ["-1006666666666#3", -1007777777777],
                     "past_mode": {"full_history": True}}
    assert "# live mirror — hand-written comment" in env.live.config_path.read_text(encoding="utf-8")
    assert "🔁 Перезапустить" in env.last_text()  # the mirror runs: the note says how to apply
    assert "🛂 Проверка доступа" in env.last_text()  # and what to check next


def test_add_direction_by_forwarded_posts_shows_the_names(env):
    _open_card(env)
    env.press("🔀 Направления")
    env.press("➕ Добавить")
    env.feed(forwarded_update(-1005555555555, "Новости <b>"))
    assert "Откуда: <b>Новости &lt;b&gt;</b>" in env.last_text()
    env.feed(forwarded_update(-1006666666666, "Моё зеркало"))
    env.type("-1007777777777")  # by id too, into the same list
    assert "<b>Моё зеркало</b>, <code>-1007777777777</code>" in env.last_text()
    env.press("✅ Готово")
    env.press("⏭ Без истории")
    assert env.data()["directions"][-1] == {"from": [-1005555555555], "to": [-1006666666666, -1007777777777]}
    assert projects.load_chat_names(env.live.key) == {-1005555555555: "Новости <b>", -1006666666666: "Моё зеркало"}
    assert "2. Новости <b> → Моё зеркало +1" in env.labels()
    assert "покажутся по имени" in env.last_text()  # -1007777777777 isn't known yet


def test_directions_show_the_last_post_and_mark_the_silent(env):
    """By the mirror's counts (stats.json): 🔇 after 7 days without a post."""
    cfg = env.data()
    cfg["directions"].append({"from": [-1005555555555], "to": [-1006666666666]})
    env.live.config_path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    first, second = cfg["directions"]
    st = stats.Stats(env.live.key, [(first["from"][0], first["to"][0]), (second["from"][0], second["to"][0])])
    st.add(first["from"][0], first["to"][0], "sent", date.today() - timedelta(days=8))
    st.add(second["from"][0], second["to"][0], "filtered", date.today() - timedelta(days=1))
    st.flush()
    _open_card(env)
    env.press("🔀 Направления")
    assert "Молчат 7 дней и больше: <b>1</b>" in env.last_text()
    rows = [b for b in env.labels() if b[:1].isdigit()]
    assert rows[0].endswith(" 🔇") and not rows[1].endswith(" 🔇")
    env.press("1. ")
    assert "🕰 Последний пост: 8 дн. назад 🔇" in env.last_text()
    env.press("⬅️ Назад")
    env.press("2. ")
    assert "🕰 Последний пост: вчера" in env.last_text()


def test_a_direction_card_shows_the_shared_settings_and_its_own(env):
    cfg = env.data()
    cfg["directions"][0]["mode"] = "forward"  # hand-written
    env.live.config_path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    _open_card(env)
    env.press("🔀 Направления")
    assert "1. -1001111111111 → -1002222222222 ✳️" in env.labels()
    env.press("1. ")
    assert {"📨 Откуда: 1", "🎯 Куда: 1"} <= set(env.labels())  # how many channels, on the buttons
    text = env.last_text()
    assert "общие для всех направлений" in text and "свои: режим «пересылка»" in text
    assert not any(b.startswith(("✏️", "↔️", "📜")) for b in env.labels())  # set once, for the project
    env.press("⏱ Пауза между отправками")
    env.type("abc")
    assert "Нужно число секунд от 0 до 60" in env.last_text()  # what to send instead
    env.type("1.5")
    assert env.data()["directions"][0]["send_delay"] == 1.5
    assert "⏱ Пауза между отправками: 1.5 с" in env.labels()
    env.press("🗑 Удалить")
    env.press("✖️ Отмена")
    assert len(env.data()["directions"]) == 1
    env.press("🗑 Удалить")
    env.press("🗑 Да, удалить")
    assert env.data()["directions"] == []
    assert configstore.backup_path(env.live).exists()


def test_find_a_direction_by_a_channels_name_or_id(env):
    cfg = env.data()
    cfg["directions"] += [{"from": [-1003333333333], "to": [-1004444444444]},
                          {"from": [-1005555555555], "to": [-1004444444444]}]
    env.live.config_path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    projects.save_chat_names(env.live.key, {-1004444444444: "Общий Канал"})
    _open_card(env)
    env.press("🔀 Направления")
    env.press("🔎 Найти")
    env.type("общий")
    assert "найдено: <b>2</b>" in env.last_text()
    assert env.labels()[:2] == ["2. -1003333333333 → Общий Канал", "3. -1005555555555 → Общий Канал"]
    env.press("3. ")
    assert "<b>№ 3</b>" in env.last_text()
    env.press("⬅️ Назад")
    env.press("🔎 Найти")
    env.feed(forwarded_update(-1001111111111, "Источник"))
    assert "найдено: <b>1</b>" in env.last_text()
    env.press("🔎 Найти")
    env.type("нет такого")
    assert "ничего не найдено" in env.last_text()


def test_a_directions_channels_are_added_and_removed_one_by_one(env):
    projects.save_chat_names(env.live.key, {-1002222222222: "Мой канал"})
    _open_card(env)
    env.press("🔀 Направления")
    assert "1. -1001111111111 → Мой канал" in env.labels()
    env.press("1. ")
    assert "🎯 Куда: <b>Мой канал</b>" in env.last_text()
    env.press("🎯 Куда")
    assert "1. <b>Мой канал</b>" in env.last_text()
    assert env.labels() == ["🗑 Мой канал", "✅ Готово", "📇 Выбрать из списка"]  # saved at once: nothing to cancel
    env.type("-1008888888888")
    assert env.data()["directions"][0]["to"] == [-1002222222222, -1008888888888]
    assert env.last_text().startswith("✅ Добавлено: <code>-1008888888888</code>.")
    assert "Перезапустить" not in env.last_text()  # said once, at ✅ Готово
    env.type("-1008888888888")
    assert "уже в списке" in env.last_text()
    env.feed(Update(update_id=int(time.time() * 1000) % 10**9, message=Message(
        message_id=99_501, date=datetime.now(), chat=Chat(id=ADMIN_ID, type="private"),
        from_user=_user(ADMIN_ID), text="от человека",
        forward_origin=MessageOriginUser(type="user", date=datetime.now(), sender_user=_user(5)),
    )))
    assert "переслано не из канала" in env.last_text()
    env.feed(forwarded_update(-1009999999999, "Ещё канал"))
    assert env.data()["directions"][0]["to"] == [-1002222222222, -1008888888888, -1009999999999]
    assert "3. <b>Ещё канал</b>" in env.last_text()
    env.press("🗑 Мой канал")
    assert env.data()["directions"][0]["to"] == [-1008888888888, -1009999999999]
    env.press("🗑 -1008888888888")
    env.press("🗑 Ещё канал")  # the last one stays
    assert env.session.of(AnswerCallbackQuery)[-1].show_alert
    assert env.data()["directions"][0]["to"] == [-1009999999999]
    env.press("✅ Готово")
    assert "<b>🔀 Направление</b>" in env.last_text()
    assert "🎯 Куда: <b>Ещё канал</b>" in env.last_text()
    assert env.last_text().startswith("✅ Сохранено. Чтобы изменения заработали, нажмите «🔁 Перезапустить»")
    env.press("🎯 Куда")
    env.press("✅ Готово")  # nothing changed: nothing to apply
    assert env.last_text().startswith("🪞 <b>Зеркало</b>")


def chat_shared_update(chat_id: int, title: str) -> Update:
    """A chat picked from the admin's own list (📺 Канал at the bottom)."""
    return Update(update_id=int(time.time() * 1000) % 10**9, message=Message(
        message_id=99_600, date=datetime.now(), chat=Chat(id=ADMIN_ID, type="private"),
        from_user=_user(ADMIN_ID), chat_shared=ChatShared(request_id=1, chat_id=chat_id, title=title),
    ))


def test_a_channel_picked_from_the_list_is_taken_like_a_forwarded_post(env):
    _open_card(env)
    env.press("🔀 Направления")
    env.press("➕ Добавить")
    assert "<b>➕ Новое направление</b> — шаг 1 из 3" in env.last_text()
    env.press("📇 Выбрать из списка")
    picker = env.sent()[-1].reply_markup
    assert isinstance(picker, ReplyKeyboardMarkup)
    bottom = [[(b.text, b.request_chat.chat_is_channel if b.request_chat else None) for b in row]
              for row in picker.keyboard]
    assert bottom == [[("📺 Канал", True), ("👥 Группа", False)],
                      [("📁 Проекты", None), ("📊 Статус", None), ("⚙️ Настройки", None)]]  # the menu stays
    env.feed(chat_shared_update(-1003333333333, "Донор <b>"))
    ack, step = env.sent()[-2:]
    assert ack.text == "📇 Выбрано: <b>Донор &lt;b&gt;</b>"
    assert [[b.text for b in row] for row in ack.reply_markup.keyboard] == [["📁 Проекты", "📊 Статус", "⚙️ Настройки"]]
    assert "шаг 2 из 3" in step.text and "Донор &lt;b&gt;" in step.text  # its title is known now
    env.feed(chat_shared_update(-1004444444444, "Моё"))
    env.press("✅ Готово")
    env.press("⏭ Без истории")
    assert env.data()["directions"][-1] == {"from": [-1003333333333], "to": [-1004444444444]}


def _bottom(sent) -> list:
    return [[b.text for b in row] for row in sent.reply_markup.keyboard]


MENU = [["📁 Проекты", "📊 Статус", "⚙️ Настройки"]]


def _open_picker(env):
    _open_card(env)
    env.press("🔀 Направления")
    env.press("➕ Добавить")
    env.press("📇 Выбрать из списка")
    assert _bottom(env.sent()[-1])[0] == ["📺 Канал", "👥 Группа"]


@pytest.mark.parametrize("leave", ["✖️ Отмена", "/cancel", "📁 Проекты", "⬅️"])
def test_a_form_left_without_a_pick_puts_the_main_menu_back(env, leave):
    _open_picker(env)
    before = len(env.sent())
    if leave == "⬅️":  # any other tap leaves the form too
        env.feed(callback_update(NavCB(s="card", p=env.live.key).pack()))
    elif leave == "✖️ Отмена":
        env.press(leave)
    else:
        env.type(leave)
    restored = [r for r in env.sent()[before:] if isinstance(r.reply_markup, ReplyKeyboardMarkup)]
    assert [(r.text, _bottom(r)) for r in restored] == [("📇 Выбор из списка закрыт — внизу снова меню.", MENU)]


def test_the_picker_again_or_start_say_nothing_extra(env):
    _open_picker(env)
    env.press("📇 Выбрать из списка")  # the prompt's button once more
    env.type("/start")
    assert not any(r.text.startswith("📇 Выбор из списка закрыт") for r in env.sent())
    assert _bottom(env.sent()[-1]) == MENU


def test_a_pick_puts_the_menu_back_once(env):
    _open_picker(env)
    env.feed(chat_shared_update(-1003333333333, "Донор"))
    env.feed(chat_shared_update(-1004444444444, "Моё"))
    env.press("✅ Готово")
    env.press("⏭ Без истории")
    assert not any(r.text.startswith("📇 Выбор из списка закрыт") for r in env.sent())


def test_a_channel_picked_with_no_form_under_way_is_not_applied(env):
    env.feed(chat_shared_update(-1003333333333, "Донор"))
    sent = env.sent()[-1]
    assert sent.text.startswith("Канал сейчас не нужен")
    assert isinstance(sent.reply_markup, ReplyKeyboardMarkup)  # the main menu back at the bottom


def test_navigating_away_leaves_the_input(env):
    def open_broadcast():
        _open_card(env)
        env.press("🔀 Направления")
        env.press("📢 Рассылка")

    open_broadcast()
    env.press("📢 Рассылать из канала")
    env.feed(callback_update(NavCB(s="tsk").pack()))  # e.g. a notification's button
    env.type("-1007777777777")  # out of the form: nothing is written
    assert "broadcast_channel" not in env.data()
    open_broadcast()
    env.press("📢 Рассылать из канала")
    env.type("-1007777777777")
    assert env.data()["broadcast_channel"] == -1007777777777
    env.press("📢 Рассылать из канала")
    env.type("-")
    assert "broadcast_channel" not in env.data()


def test_params_toggles(env):
    _open_card(env)
    env.press("⚙️ Настройки проекта")
    assert "✏️ Повторять правки: выкл" in env.labels()
    env.press("✏️ Повторять правки")
    assert env.data()["disable_edit"] is False
    env.press("↔️ Как публиковать")
    assert env.data()["mode"] == "forward"


def test_filter_editor_add_and_remove(env):
    _open_card(env)
    env.press("🧹 Фильтры")
    env.press("1. Пропускать посты со словами")
    assert "реклама" in env.last_text()
    env.press("➕ Добавить")
    env.type("спам\nказино")
    assert set(env.data()["filters"][0]["SkipWithKeywordsFilter"]["keywords"]) == {"реклама", "спам", "казино"}
    env.press("🗑 1. казино")
    assert set(env.data()["filters"][0]["SkipWithKeywordsFilter"]["keywords"]) == {"реклама", "спам"}


def test_add_filters_with_and_without_a_required_value(env):
    _open_card(env)
    env.press("🧹 Фильтры")
    env.press("➕ Добавить фильтр")
    env.press("Пропускать посты с любыми ссылками")
    assert [projects_filter_name(f) for f in env.data()["filters"]] == ["SkipWithKeywordsFilter", "SkipUrlFilter"]
    env.press("➕ Добавить фильтр")
    env.press("Замена слов")
    assert "что =&gt; на что" in env.last_text()
    env.type("реклама => промо")
    assert env.data()["filters"][-1] == {"KeywordReplaceFilter": {"keywords": {"реклама": "промо"}}}


def projects_filter_name(entry) -> str:
    return configedit.filter_name(entry)


def test_filter_card_toggles_moves_and_deletes(env):
    _open_card(env)
    env.press("🧹 Фильтры")
    env.press("➕ Добавить фильтр")
    env.press("Пропускать посты с любыми ссылками")
    env.press("2. Пропускать посты с любыми ссылками")
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
    env.press("Прятать ссылки")
    env.press("2. Прятать ссылки")
    env.press("📝 Только эти @…")
    assert "с <code>@</code>" in env.last_text()
    env.type("@spam\n@ads")
    assert env.data()["filters"][1] == {"UrlMessageFilter": {"filter_mention": {"@spam", "@ads"}}}
    env.press("🗑 1. @ads")
    env.press("🗑 1. @spam")
    assert env.data()["filters"][1] == {"UrlMessageFilter": {}}
    assert "⬜ убирать @упоминания" in env.labels()  # a bool again
    env.press("⬅️ Назад")
    env.press("➕ Добавить фильтр")
    env.press("Водяной знак")
    env.press("3. Водяной знак")
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
    env.press("Пауза: не копировать ничего")
    own = [projects_filter_name(f) for f in env.data()["directions"][0]["filters"]]
    assert own == ["SkipWithKeywordsFilter", "SkipAllFilter"]
    assert "скопированы" in env.last_text()


def test_history_from_a_date_written_as_in_russia(env):
    _open_card(env)
    env.press("⏪ Старые посты")
    env.press("📜 Что копировать")
    env.press("📅 С даты")
    env.type("31.02.2024")  # no such day: refused, asked again
    assert "Нужна дата <code>31.01.2024</code>" in env.last_text()
    env.type("31.01.2024")
    # Moscow midnight, its offset kept: a bare date would be UTC to Telethon, 3 hours off
    assert env.data()["directions"][0]["past_mode"]["since_date"] == "2024-01-31T00:00:00+03:00"
    assert "📜 Что копировать: с 31.01.2024" in env.labels()  # shown as typed


def test_one_history_and_one_pause_for_every_direction(env):
    cfg = env.data()
    cfg["directions"].append({"from": [-1003333333333], "to": [-1004444444444]})
    env.live.config_path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    _open_card(env)
    env.press("⏪ Старые посты")
    assert "📜 Что копировать: нет" in env.labels()
    assert not any(b.startswith("⏱") for b in env.labels())  # nothing to pause yet
    env.press("📜 Что копировать")
    env.press("📚 Вся история")
    assert [d["past_mode"] for d in env.data()["directions"]] == [{"full_history": True}] * 2
    assert "📜 Что копировать: вся история" in env.labels()
    env.press("⏱ Пауза для старых постов")
    env.type("2")
    assert [d["past_mode"] for d in env.data()["directions"]] == [{"full_history": True, "send_delay": 2}] * 2
    env.press("📜 Что копировать")
    env.press("🔢 Последние N")
    env.type("100")
    assert [d["past_mode"] for d in env.data()["directions"]] == [{"last_n": 100, "send_delay": 2}] * 2
    cfg = env.data()
    del cfg["directions"][1]["past_mode"]
    env.live.config_path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    env.press("🔄 Обновить")
    assert "📜 Что копировать: разное (у 1 из 2 направлений)" in env.labels()


# ── ⏪ Старые посты, 🛠 Инструменты, 📊 Статус ────────────────────────


def test_a_paced_history_is_the_mirrors_and_stops_nothing(env):
    _open_card(env)
    env.press("⏪ Старые посты")
    assert not any(b.startswith("🐢") for b in env.labels())  # nothing to pace yet
    env.press("📜 Что копировать")
    env.press("📚 Вся история")
    assert "🐢 Темп: сразу" in env.labels()
    env.press("🐢 Темп")
    env.type("пять")
    assert "5/45" in env.last_text()  # refused, asked again
    env.type("5/45")
    assert env.data()["directions"][0]["past_mode"] == {"full_history": True, "drip": {"posts": 5, "minutes": 45}}
    labels = env.labels()
    assert "🐢 Темп: 5 постов за 45 мин" in labels
    assert not any(b.startswith(("▶️", "⏸", "⏱")) for b in labels)  # the mirror copies it: no unit to start
    # Regression: «копируется» while the mirror, started before the pace, didn't drip at all
    assert "⏸ ждёт перезапуска зеркала" in env.last_text()
    _open_card(env)
    assert "копируются порциями" not in env.last_text()
    assert "Изменения ещё не применены" in env.last_text()
    env.fake.journal = ("INFO  2026-11-23 04:00:05 [past.py:1]:past_mode: [PastMode] drip: "
                        "1 channel pair(s) taking turns, alongside the live mirror")
    env.press("🔄 Обновить")
    assert "🐢 Старые посты копируются порциями: 5 постов за 45 мин" in env.last_text()
    env.feed(callback_update(NavCB(s="rpl", p=env.live.key).pack()))
    assert "копируется порциями вместе с зеркалом" in env.last_text()
    _open_card(env)
    # Regression: both kept saying so for weeks after the drip had finished
    env.fake.journal = "INFO  2026-11-23 04:00:05 [past.py:1]:past_mode: [PastMode] drip: done"
    env.press("🔄 Обновить")
    assert "копируются порциями" not in env.last_text()
    env.feed(callback_update(NavCB(s="rpl", p=env.live.key).pack()))
    assert "✅ старые посты скопированы" in env.last_text()
    # how many channel pairs are done, while under way
    env.fake.journal = ("INFO  2026-11-23 04:00:05 [past.py:1]:past_mode: [PastMode] -1001→-1002: "
                        "sent a post, gone through 12/340, next in 9min · 3/29 pair(s) done")
    env.press("🔄 Обновить")
    assert "🐢 копируется порциями вместе с зеркалом, готово пар каналов: 3 из 29" in env.last_text()
    _open_card(env)
    assert "🐢 Старые посты копируются порциями: 5 постов за 45 мин, готово пар каналов: 3 из 29" \
        in env.last_text()
    # Regression: one pair giving up showed the whole drip stopped, the others still copying
    env.fake.journal = ("ERROR 2026-11-23 04:00:05 [past.py:1]:telemirror: [PastMode] -1001→-1002: "
                        "gave up copying its history — the other pairs and the live mirror go on, "
                        "tried again next start. RuntimeError: x")
    env.press("🔄 Обновить")
    assert "остановилось с ошибкой" not in env.last_text()
    # Regression: «копируется» though it had given up
    env.fake.journal = ("WARNING 2026-11-23 04:00:05 [past.py:1]:past_mode: [PastMode] drip: 1 pair(s) "
                        "gave up — drip stopped, the live mirror goes on, tried again next start")
    env.press("🔄 Обновить")
    assert "⚠️ Копирование старых постов остановилось с ошибкой" in env.last_text()
    env.feed(callback_update(NavCB(s="rpl", p=env.live.key).pack()))
    assert "⚠️ остановилось с ошибкой — продолжит после перезапуска зеркала" in env.last_text()
    env.fake.journal = "line one\nline <two>"
    _open_card(env)
    env.feed(callback_update(NavCB(s="rpl", p=env.live.key).pack()))
    assert "Изменения ещё не применены" in env.last_text()  # the mirror started before the save
    env.press("🔁 Перезапустить зеркало")
    assert "Новые настройки начнут действовать" in env.last_text()
    env.press("✅ Да")
    assert any("restart" in c and env.live.live_unit in c for c in env.fake.calls)
    env.feed(callback_update(NavCB(s="rpl", p=env.live.key).pack()))
    env.press("🐢 Темп")
    env.type("-")
    assert env.data()["directions"][0]["past_mode"] == {"full_history": True}
    assert "▶️ Начать копирование" in env.labels()
    # dropped while the mirror still drips (its run's journal says so): it's to be restarted
    env.fake.journal = ("INFO  2026-11-23 04:00:05 [past.py:1]:past_mode: [PastMode] -1001→-1002: "
                        "sent a post, gone through 12/340, next in 9min")
    env.press("🔄 Обновить")
    assert "Изменения ещё не применены" in env.last_text()
    env.fake.journal = ""  # no drip in the mirror's run: nothing to restart for
    env.press("🔄 Обновить")
    assert "Изменения ещё не применены" not in env.last_text()
    env.fake.journal = "INFO  2026-11-23 04:00:05 [past.py:1]:past_mode: [PastMode] drip: done"
    env.press("🔄 Обновить")
    assert "Изменения ещё не применены" not in env.last_text()  # its drip had nothing left
    env.press("🐢 Темп")
    env.type("30с")  # in seconds
    assert env.data()["directions"][0]["past_mode"] == {"full_history": True, "drip": {"seconds": 30}}
    assert "🐢 Темп: 1 пост раз в 30 с" in env.labels()


def test_an_old_start_button_doesnt_stop_the_mirror_once_a_pace_is_set(env):
    """Regression: ▶️ on a screen drawn before 🐢 Темп started the replay unit —
    the mirror and its drip stopped for a run that had nothing to do."""
    cfg = env.data()
    cfg["directions"][0]["past_mode"] = {"full_history": True}
    env.live.config_path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    _open_card(env)
    env.press("⏪ Старые посты")
    cfg["directions"][0]["past_mode"]["drip"] = {"posts": 5, "minutes": 45}
    env.live.config_path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    env.press("▶️ Начать")
    assert env.session.of(AnswerCallbackQuery)[-1].text == texts.STALE_BUTTON
    assert not any(env.live.past_unit in c for c in env.fake.calls if "start" in c)


def test_a_pace_set_for_all_isnt_a_directions_own(env):
    """Regression: 🐢 Темп (and ⏱ the pause) is written into every direction —
    each was marked ✳️ «свои настройки в файле»."""
    from bot.routers.directions import own_settings
    one = {"past_mode": {"full_history": True, "send_delay": 2, "drip": {"posts": 5, "minutes": 45}}}
    other = {"past_mode": {"full_history": True, "send_delay": 2, "drip": {"posts": 5, "minutes": 45}}}
    assert own_settings(one, {"directions": [one, other]}) == []
    other["past_mode"]["drip"] = {"minutes": 45, "posts": 5}  # the same pace, its keys in another order
    assert own_settings(one, {"directions": [one, other]}) == []
    other["past_mode"] = {"full_history": True, "drip": {"posts": 1, "minutes": 10}}  # hand-written
    assert len(own_settings(one, {"directions": [one, other]})) == 2
    # the default given or not: one pause, as ⏪ tells it
    one["past_mode"], other["past_mode"] = {"full_history": True, "send_delay": 0.5}, {"full_history": True}
    assert own_settings(one, {"directions": [one, other]}) == []


def test_a_replay_running_at_once_stays_stoppable_once_a_pace_is_set(env):
    """Regression: 🐢 Темп set while ▶️ ran it all at once hid ⏸ — «ждёт запуска зеркала»."""
    cfg = env.data()
    cfg["directions"][0]["past_mode"] = {"full_history": True, "drip": {"posts": 5, "minutes": 45}}
    env.live.config_path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    env.fake.states[env.live.past_unit] = "active"
    _open_card(env)
    env.press("⏪ Старые посты")
    assert "ждёт запуска зеркала" not in env.last_text()
    assert any(b.startswith("⏸") for b in env.labels())


def test_replay_needs_history_then_pauses_the_mirror(env):
    _open_card(env)
    env.press("⏪ Старые посты")
    assert "👉 Сначала выберите, какие посты копировать: «📜 Что копировать»." in env.last_text()
    env.press("▶️ Начать")
    assert "Не выбрано, какие старые посты" in env.session.of(AnswerCallbackQuery)[-1].text
    cfg = env.data()
    cfg["directions"][0]["past_mode"] = {"full_history": True}
    env.live.config_path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    env.fake.journal = ""  # the mirror doesn't drip
    env.press("🔄 Обновить")
    # Regression: any change since the mirror's start asked to restart it — ▶️ reads the config itself
    assert "Изменения ещё не применены" not in env.last_text()
    env.press("▶️ Начать")
    assert "будет приостановлено" in env.last_text()
    env.press("✅ Да")
    assert ["systemctl", "--no-block", "start", env.live.past_unit] in env.fake.calls
    assert turns.load()[0]["resume"] == [env.live.live_unit]


def test_maintenance_dry_run_writes_the_task_env_file(env):
    _open_card(env)
    env.press("🛠 Инструменты")
    env.press("📌 Закрепы")
    env.press("⬜ Только добавлять")
    assert "☑️ Только добавлять" in " ".join(env.labels())
    assert not any(label.startswith("▶️ Выполнить") for label in env.labels())  # no dry run yet
    assert "«▶️ Выполнить» появится здесь после успешной проверки" in env.last_text()  # said where it is
    env.press("🔍 Проверить")
    env.press("✅ Да")
    env_file = (env.tmp / "run" / f"{env.live.key}.env").read_text()
    assert env_file == "TASK_MODULE=sync_pins\nTASK_ARGS=--additive --dry-run\n"
    assert ["systemctl", "--no-block", "start", env.live.task_unit] in env.fake.calls


@pytest.mark.parametrize("screen, module", [("🕶 Анонимность", "anonymize_groups"),
                                            ("🧨 Очистка каналов", "clear_channels")])
def test_maintenance_scripts_without_flags(env, screen, module):
    _open_card(env)
    env.press("🛠 Инструменты")
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
    from bot.routers.maintenance import config_sha

    env.dp["runtime"].launches[(env.live.key, "cc")] = Launch(("--dry-run",), True, 0.0, config_sha(env.live))
    _open_card(env)
    env.press("🛠 Инструменты")
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
    from bot.routers.maintenance import can_run_real, config_sha
    from bot.systemd import parse_show
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
    from bot.routers.maintenance import can_run_real, config_sha
    from bot.systemd import parse_show
    from tests._panel import SHOW

    runtime = env.dp["runtime"]
    st = parse_show(SHOW.format(active="inactive", sub="dead", result="success"))
    runtime.launches[(env.live.key, "cc")] = Launch(("--dry-run",), True, 1_600_000_000.0, config_sha(env.live))
    assert can_run_real("cc", env.live, runtime, st)
    env.live.config_path.write_text(LIVE_YAML + "# a recipient added since\n", encoding="utf-8")
    assert not can_run_real("cc", env.live, runtime, st)


def test_a_check_stopped_halfway_does_not_unlock_the_real_run(env):
    """systemd counts a stop by SIGTERM (⏹, a mirror started over it) as
    Result=success: the check's process must have exited 0 by itself."""
    from bot.routers.maintenance import can_run_real, config_sha
    from bot.systemd import parse_show
    from tests._panel import SHOW

    runtime = env.dp["runtime"]
    runtime.launches[(env.live.key, "cc")] = Launch(("--dry-run",), True, 1_600_000_000.0, config_sha(env.live))
    killed = SHOW.format(active="inactive", sub="dead", result="success").replace(
        "ExecMainCode=1\nExecMainStatus=0", "ExecMainCode=2\nExecMainStatus=15")
    st = parse_show(killed)
    assert st.result == "success" and not st.completed
    assert not can_run_real("cc", env.live, runtime, st)


def test_a_confirmed_run_is_checked_again(env):
    """Between the question and «Да» the task unit may have started (another
    admin, another screen): «Да» then starts nothing."""
    _open_card(env)
    env.press("🛠 Инструменты")
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
    env.press("🛠 Инструменты")
    env.press("📌 Закрепы")
    env.press("📏 Лимит")
    env.type("50")
    env.press("📍 Выбрать источники")
    env.type("-1009999999999")
    assert "не источники проекта" in env.last_text()
    env.type("-1001111111111")
    assert "📍 Выбрать источники: 1" in " ".join(env.labels())
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
    assert "🩺 Оповещение о сбоях: выкл" in env.labels()
    env.press("🩺 Оповещение о сбоях")  # a switch: no question, one tap back
    assert ["systemctl", "--no-block", "enable", "--now", "telemirror-health.timer"] in env.fake.calls
    assert env.last_text().startswith("▶️ Включено: 🩺 Оповещение о сбоях.")
    env.fake.states["telemirror-restart.timer"] = "active"
    env.press("🔄 Обновить")
    env.press("🔁 Перезапуск по расписанию")
    assert "только после" in env.last_text()  # what turning it off changes, in its note
    assert ["systemctl", "--no-block", "disable", "--now", "telemirror-restart.timer"] in env.fake.calls


def test_selfcheck_screen(env, monkeypatch):
    monkeypatch.setattr(selfcheck, "run", lambda: [
        selfcheck.Check(selfcheck.OK, "База", "подключение есть, таблицы на месте"),
        selfcheck.Check(selfcheck.FAIL, "🪞 Зеркало: настройки", "bad <mode>"),
    ])
    env.type("⚙️ Настройки")
    env.press("🧾 Диагностика сервера")
    assert texts.SELFCHECK_WAIT in [str(r.text) for r in env.sent()]  # while it runs
    text = env.last_text()
    assert "✅ 1 · ⚠️ 0 · ❌ 1" in text and "❌ 🪞 Зеркало: настройки — bad &lt;mode&gt;" in text
    assert env.labels() == ["🔄 Обновить", "⬅️ Назад"]


def test_access_check_shows_its_report_and_runs_without_a_real_run(env):
    report = {"at": time.time(), "chats": [
        {"id": -1001111111111, "roles": ["source"], "title": "Донор", "ok": True, "reason": "", "note": "noforwards"},
        {"id": -1002222222222, "roles": ["target"], "title": "Зеркало <x>", "ok": False, "reason": "cannot_post",
         "note": ""},
    ]}
    projects.access_report_path(env.live.key).write_text(json.dumps(report), encoding="utf-8")
    _open_card(env)
    env.press("🛠 Инструменты")
    env.press("🛂 Проверка доступа")
    text = env.last_text()
    assert "✅ 1 · ❌ 1" in text and "Зеркало &lt;x&gt;" in text and "нет права публиковать" in text
    assert "запрещено сохранение" in text
    assert not any(label.startswith("▶️ Выполнить") for label in env.labels())
    env.press("🔍 Проверить")
    env.press("✅ Да")
    env_file = (env.tmp / "run" / f"{env.live.key}.env").read_text()
    assert env_file == "TASK_MODULE=check_access\nTASK_ARGS=\n"


def test_tasks_and_unit_card(env):
    env.type("📊 Статус")
    assert "🪞 Зеркало · зеркало · 🟢 работает" in env.labels()  # on its button, not repeated in the text
    assert "🟢" not in env.last_text()
    env.press("🪞 Зеркало · зеркало")
    text = env.last_text()
    assert "line &lt;two&gt;" in text  # the journal is escaped
    # managed where it's run from: the button names that screen
    assert env.labels() == ["📁 Проект ›", "🔄 Обновить", "⬅️ Назад"]
    env.press("📁 Проект ›")
    assert env.last_text().startswith("🪞 <b>Зеркало</b>\n")  # the project's card
    env.feed(callback_update(NavCB(s="unit", p=env.live.key, i=1).pack()))
    env.press("⏪ Старые посты ›")
    assert "<b>⏪ Старые посты</b>" in env.last_text()


# ── 💾 Файл настроек ────────────────────────────────────────────────────────


def test_download_upload_and_rollback(env):
    _open_card(env)
    env.press("⚙️ Настройки проекта")
    env.press("💾 Файл настроек")
    env.press("📥 Скачать")
    assert env.session.of(SendDocument)[-1].document.data == LIVE_YAML.encode()
    new = "directions:\n  - from: [-1005555555555]\n    to: [-1006666666666]\n"
    env.press("📤 Загрузить")
    env.upload("mirror.config.yml", new.encode())
    assert "Что изменится" in env.last_text()
    assert env.live.config_path.read_text(encoding="utf-8") == LIVE_YAML
    env.press("✅ Да")
    assert env.live.config_path.read_text(encoding="utf-8") == new
    assert "Настройки заменены" in env.last_text()
    env.press("↩️ Откатить")
    env.press("✅ Да")
    assert env.live.config_path.read_text(encoding="utf-8") == LIVE_YAML


def test_a_broken_file_can_still_be_rolled_back(env):
    _open_card(env)
    env.press("⚙️ Настройки проекта")
    env.press("↔️ Как публиковать")  # creates a good .bak
    env.live.config_path.write_text("directions: [unclosed\n", encoding="utf-8")
    _open_card(env)
    assert "Не удалось прочитать файл настроек" in env.last_text()
    env.press("⚙️ Настройки проекта")
    env.press("💾 Файл настроек")
    env.press("↩️ Откатить")
    env.press("✅ Да")
    assert yaml.safe_load(env.live.config_path.read_text(encoding="utf-8"))["directions"]


# ── 👤 Аккаунты ─────────────────────────────────────────────────────────────


@pytest.fixture
def importing(monkeypatch):
    """📤 Загрузить сессию with Telethon scripted (tests/test_session_import.py's
    client) and a short album wait."""
    from telemirror.misc import session_import
    from tests.test_session_import import FakeClient as ImportClient

    monkeypatch.setattr(settings, "ALBUM_LATENCY_SEC", 0.05)
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
    monkeypatch.setattr(accounts, "new_tdesktop_client", lambda: client)
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
    assert "облачный пароль" in env.last_text()
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
    monkeypatch.setattr(accounts, "new_tdesktop_client", lambda: client)
    env.type("⚙️ Настройки")
    env.press("👤 Аккаунты")
    env.press("🔑 Войти по номеру")
    env.type("+79994443322")
    env.type("0 0 0 0 0")
    assert "Код больше не действует" in env.last_text()
    env.press("📲 Отправить код заново")
    assert client.codes_sent == 2 and "Новый код отправлен" in env.last_text()
    env.type("1 2 3 4 5")  # checked against the new code's hash
    assert (env.tmp / "sessions" / "79994443322.jsession").exists()
    assert "✅ Вход выполнен" in env.last_text()


def test_a_project_whose_session_is_gone_says_where_to_fix_it(env):
    (env.tmp / SESSION).unlink()
    _open_card(env)
    assert "Вход в аккаунт проекта не найден" in env.last_text()
    env.press("🔁 Перезапустить")  # a restart needs no session check: only start / runs do
    env.press("✖️ Отмена")
    env.press("⚙️ Настройки проекта")
    env.press("↔️ Как публиковать")
    assert "⚙️ Настройки проекта → 👤 Аккаунт" in env.last_text()
    assert "mode" not in env.data()  # nothing written
    env.press("⬅️ Назад")  # the refusal's ⬅️: back to ⚙️ Настройки проекта
    env.press("⬅️ Назад")
    env.press("⏪ Старые посты")
    env.press("▶️ Начать")
    answer = env.session.of(AnswerCallbackQuery)[-1]
    assert answer.show_alert and "Вход в аккаунт проекта не найден" in answer.text


# ── shared mechanisms (pass 27): one project lookup for every way in, one
# retry for a refused value, confirmations only where something is stopped or
# lost, ⬅️ back to the page it came from, nothing kept for abandoned forms ──

# ── a deleted project, whichever way in ─────────────────────────────────────


def _delete_live(env):
    projects.delete_project(env.live.key)


def test_a_deleted_projects_screen_shows_the_project_list(env):
    _delete_live(env)
    env.feed(callback_update(NavCB(s="dirs", p=env.live.key).pack()))
    assert env.last_text().startswith("⛔ Проект не найден")
    assert "<b>📁 Проекты</b>" in env.last_text()


def test_a_deleted_projects_button_is_answered(env):
    _delete_live(env)
    env.feed(callback_update(ActCB(a="dir_add", p=env.live.key).pack()))
    assert env.session.of(AnswerCallbackQuery)[-1].text.startswith("⛔ Проект не найден")


def test_a_deleted_projects_confirmation_and_input_are_answered(env):
    _open_card(env)
    env.press("⚙️ Настройки проекта")
    env.press("🏷 Переименовать")
    _delete_live(env)
    env.type("Другое имя")
    assert env.last_text().startswith("⛔ Проект не найден")
    assert env.last_kb().inline_keyboard[0][0].callback_data == NavCB(s="prj").pack()


# ── a refused value: one way to say it ──────────────────────────────────────


def test_a_refused_value_is_asked_again(env):
    _open_card(env)
    env.press("🔀 Направления")
    env.press("1. ")
    env.press("⏱ Пауза между отправками")
    env.type("сто")
    assert env.last_text() == ("⚠️ Нужно число секунд от 0 до 60, например <code>1.5</code>, получено: "
                               "<code>сто</code>\nПришлите ещё раз:")
    env.type("2")
    assert env.data()["directions"][0]["send_delay"] == 2


# ── confirmations: only when something is stopped or lost ──────────────────


def _stop_the_mirror(env):
    env.fake.states[env.live.live_unit] = "inactive"


def test_a_check_alone_on_its_session_starts_without_a_question(env):
    _stop_the_mirror(env)
    _open_card(env)
    env.press("🛠 Инструменты")
    env.press("🛂 Проверка доступа")
    env.press("🔍 Проверить")
    assert ["systemctl", "--no-block", "start", env.live.task_unit] in env.fake.calls
    assert env.last_text().startswith("▶️ Проверка запущена.")


def test_a_replay_alone_on_its_session_starts_without_a_question(env):
    _stop_the_mirror(env)
    cfg = env.data()
    cfg["directions"][0]["past_mode"] = {"full_history": True}
    env.live.config_path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    _open_card(env)
    env.press("⏪ Старые посты")
    env.press("▶️ Начать")
    assert ["systemctl", "--no-block", "start", env.live.past_unit] in env.fake.calls
    assert env.last_text().startswith("▶️ Запускается.")


def test_a_real_run_always_asks(env):
    from bot.routers.maintenance import config_sha

    _stop_the_mirror(env)
    env.dp["runtime"].launches[(env.live.key, "rs")] = Launch(("--dry-run",), True, 0.0, config_sha(env.live))
    _open_card(env)
    env.press("🛠 Инструменты")
    env.press("🔒 Запрет копирования")
    env.press("▶️ Выполнить")
    assert env.labels() == ["✅ Да", "✖️ Отмена"]


# ── navigation ──────────────────────────────────────────────────────────────


def _kb_navs(env) -> list:
    kb: InlineKeyboardMarkup = env.last_kb()
    return [NavCB.unpack(b.callback_data) for row in kb.inline_keyboard for b in row
            if b.callback_data and b.callback_data.startswith("n:")]


def test_back_returns_to_the_page_of_the_list(env, monkeypatch):
    monkeypatch.setattr(settings, "PAGE_SIZE", 1)
    projects.create_project("Второй", "🚀", "sessions/79990000000.jsession")
    env.type("📁 Проекты")
    env.press("▶️")  # page 2
    env.press("🪞 Зеркало")
    env.press("⚙️ Настройки проекта")
    env.press("💾 Файл настроек")
    assert NavCB(s="mng", p=env.live.key, pg=1) in _kb_navs(env)  # ⬅️ Назад
    env.press("⬅️ Назад")
    assert NavCB(s="card", p=env.live.key, pg=1) in _kb_navs(env)
    env.press("⬅️ Назад")
    assert NavCB(s="prj", p=env.live.key, pg=1) in _kb_navs(env)


def test_a_maintenance_journal_goes_back_to_its_screen(env):
    _open_card(env)
    env.press("🛠 Инструменты")
    env.press("📌 Закрепы")
    env.press("📄 Журнал")
    assert "line &lt;two&gt;" in env.last_text() and "<b>📌 Закрепы</b>" in env.last_text()
    navs = _kb_navs(env)
    assert NavCB(s="sp", p=env.live.key) in navs  # 🔄 Обновить: the same screen
    assert NavCB(s="mnt", p=env.live.key) in navs  # ⬅️ Назад: its parent


def test_a_direction_filters_card_shows_where_it_is(env):
    cfg = env.data()
    cfg["directions"][0]["filters"] = [{"SkipWithKeywordsFilter": {"keywords": ["x"]}}]
    env.live.config_path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    _open_card(env)
    env.press("🔀 Направления")
    env.press("1. ")
    env.press("🧹 Фильтры направления")
    env.press("1. Пропускать посты со словами")
    assert "<b>🧹 Фильтры направления</b> › <b>🧹 Фильтр</b>" in env.last_text()
    env.press("🗑 Удалить фильтр")
    env.press("✖️ Отмена")
    assert "<b>Пропускать посты со словами</b> · направление № 1" in env.last_text()  # back on its card


# ── nothing kept for long ───────────────────────────────────────────────────


def test_a_stranger_leaves_no_fsm_record(env):
    storage: PanelStorage = env.dp.fsm.storage
    env.feed(message_update("/start", uid=STRANGER_ID))
    env.feed(callback_update(NavCB(s="prj").pack(), uid=STRANGER_ID))
    assert storage.storage == {}


def test_a_finished_form_leaves_no_fsm_record(env):
    storage: PanelStorage = env.dp.fsm.storage
    _open_card(env)
    env.press("⚙️ Настройки проекта")
    env.press("🏷 Переименовать")
    assert storage.storage
    env.type("/cancel")
    assert storage.storage == {}


class _Client:
    disconnected = 0

    async def disconnect(self):
        _Client.disconnected += 1


def test_a_pending_sign_in_is_dropped_after_its_ttl(monkeypatch):
    monkeypatch.setattr(settings, "PENDING_TTL_SEC", 0.01)
    _Client.disconnected = 0

    async def scenario():
        await pending.put(1, pending.Login(_Client(), "7"))
        await asyncio.sleep(0.05)
        return pending.get(1, pending.Login)

    assert run(scenario()) is None
    assert _Client.disconnected == 1


def test_a_new_item_replaces_and_close_all_disconnects(monkeypatch):
    monkeypatch.setattr(settings, "PENDING_TTL_SEC", 60)
    _Client.disconnected = 0

    async def scenario():
        await pending.put(1, pending.Login(_Client(), "7"))
        await pending.put(1, pending.Upload({"a": b"x"}))  # the sign-in is dropped
        await pending.put(2, pending.Login(_Client(), "8"))
        await pending.close_all()
        return pending.get(1, pending.Upload), pending.get(2, pending.Login)

    assert run(scenario()) == (None, None)
    assert _Client.disconnected == 2


def test_an_album_wait_cancelled_leaves_no_bucket(monkeypatch):
    monkeypatch.setattr(settings, "ALBUM_LATENCY_SEC", 10)
    middleware = AlbumMiddleware()

    class Item:
        media_group_id, message_id = "g", 1

    async def handler(event, data):
        return None

    async def scenario():
        task = asyncio.create_task(middleware(handler, Item(), {}))
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    run(scenario())
    assert middleware._albums == {}


def test_a_deleted_project_is_forgotten_by_the_runtime(env):
    runtime = Runtime()
    runtime.mark_started(env.live.live_unit)
    runtime.flags(env.live.key).add("--additive")
    runtime.launches[(env.live.key, "sp")] = Launch((), True, 0.0)
    runtime.launches[("other", "sp")] = Launch((), True, 0.0)
    runtime.forget(env.live)
    assert runtime.cooldown_left(env.live.live_unit) == 0
    assert runtime.flags(env.live.key) == set()
    assert list(runtime.launches) == [("other", "sp")]


def test_every_screen_opens_without_an_internal_error(env):
    """A walk through the whole registry: every screen renders through the real
    Dispatcher (its project's, its list's first item), and every keyboard's
    navigation leads somewhere that renders too."""
    from bot import registry

    cfg = env.data()
    cfg["directions"][0]["filters"] = [{"SkipWithKeywordsFilter": {"keywords": ["x"]}}]
    cfg["directions"][0]["past_mode"] = {"full_history": True}
    env.live.config_path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    seen = set()
    for screen in registry.SCREENS.values():
        nav = NavCB(s=screen.id, p=env.live.key if screen.project else "",
                    i=0 if screen.id in ("dir", "dflt", "acct", "fv", "unit") else -1)
        env.feed(callback_update(nav.pack()))
        assert "Внутренняя ошибка" not in env.last_text(), screen.id
        seen.add(screen.id)
        for target in _kb_navs(env):
            env.feed(callback_update(target.pack()))
            assert "Внутренняя ошибка" not in env.last_text(), (screen.id, target)
    assert seen == set(registry.SCREENS)


def test_back_from_a_directions_filter_card_reaches_the_directions_page(env, monkeypatch):
    monkeypatch.setattr(settings, "PAGE_SIZE", 1)
    cfg = env.data()
    second = {"from": [-1003333333333], "to": [-1004444444444],
              "filters": [{"SkipWithKeywordsFilter": {"keywords": ["x"]}}]}
    cfg["directions"].append(second)
    env.live.config_path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    env.feed(callback_update(NavCB(s="dir", p=env.live.key, i=1, pg=1).pack()))
    env.press("🧹 Фильтры направления")
    env.press("1. Пропускать посты со словами")
    env.press("⬅️ Назад")  # → the direction's filters
    env.press("⬅️ Назад")  # → the direction
    assert NavCB(s="dirs", p=env.live.key, i=1, pg=1) in _kb_navs(env)


# ── words for people: filters by their names, what to do next ───────────────


def test_filters_are_named_for_people_and_rare_settings_are_folded(env):
    _open_card(env)
    env.press("🧹 Фильтры")
    assert "<b>Пропускать посты со словами</b> — <i>слова: реклама</i>" in env.last_text()
    env.press("➕ Добавить фильтр")
    env.press("Водяной знак")
    env.press("2. Водяной знак")
    text = env.last_text()
    assert "точность поиска знака" not in text and "<code>WatermarkRemovalFilter</code>" in text
    env.press("🔬 Тонкая настройка")
    assert "точность поиска знака" in env.last_text()
    env.press("📝 точность поиска знака")
    env.type("0.4")
    assert env.data()["filters"][1] == {"WatermarkRemovalFilter": {"match_threshold": 0.4}}
    assert "точность поиска знака" in env.last_text()


def test_the_card_says_what_to_do_next(env):
    _stop_the_mirror(env)
    _open_card(env)
    assert "👉 <b>Что дальше:</b> нажмите «▶️ Запустить»" in env.last_text()
    empty = projects.create_project("Пустой", "🚀", SESSION)
    _open_card(env, empty)
    assert "👉 <b>Что дальше:</b> добавьте, откуда и куда копировать" in env.last_text()


def test_a_filter_card_describes_only_its_own_buttons(env):
    _open_card(env)
    env.press("🧹 Фильтры")
    env.press("1.")
    text = env.last_text()
    assert "включить или выключить" not in text and "задать своё" not in text and "порядок" not in text
    env.press("⬅️ Назад")
    env.press("➕ Добавить фильтр")
    env.press("Пропускать посты с любыми ссылками")
    env.press("2.")
    text = env.last_text()
    assert "<b>☑️ / ⬜</b> — включить или выключить" in text and "<b>⬆️ Выше</b> — порядок" in text


def test_an_accounts_card_puts_the_technical_details_last(env):
    env.type("⚙️ Настройки")
    env.press("👤 Аккаунты")
    env.press("👤 +79990000000")
    text = env.last_text()
    assert "Проекты: 🪞 Зеркало — пока аккаунт в них, удалить его нельзя" in text
    assert text.index("Проекты:") < text.index("<blockquote expandable>Технические подробности: файл <code>sessions/")


def test_a_running_tool_can_be_stopped_on_its_screen(env):
    env.fake.states[env.live.task_unit] = "active"
    _open_card(env)
    env.press("🛠 Инструменты")
    env.press("📌 Закрепы")
    env.press("⏹ Остановить")
    env.press("✅ Да")
    assert ["systemctl", "--no-block", "stop", env.live.task_unit] in env.fake.calls
    env.fake.states[env.live.task_unit] = "inactive"
    env.press("🔄 Обновить")
    assert "⏹ Остановить" not in env.labels()


def test_the_broadcast_is_set_in_the_directions(env):
    _open_card(env)
    env.press("🔀 Направления")
    env.press("📢 Рассылка")
    assert "во все ваши каналы" in env.last_text()
    env.press("📢 Рассылать из канала")
    env.feed(forwarded_update(-1009999999999, "Объявления"))
    assert env.data()["broadcast_channel"] == -1009999999999
    assert "📢 Рассылать из канала: <b>Объявления</b>" in env.last_text()  # back on 📢 Рассылка


def test_channels_are_named_wherever_the_bot_shows_them(env):
    cfg = env.data()
    cfg["broadcast_channel"] = -1003926294676
    cfg["filters"].append({"WatermarkRemovalFilter": {"channels": [-1001111111111]}})
    env.live.config_path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    _open_card(env)
    env.press("🔀 Направления")
    env.press("📢 Рассылка")
    assert "📢 Рассылать из канала: <code>-1003926294676</code>" in env.last_text()
    assert "покажутся по имени" in env.last_text()  # not known yet: says when it will be
    projects.save_chat_names(env.live.key, {-1003926294676: "Объявления", -1001111111111: "Склад"})
    env.press("⬅️ Назад")
    env.press("📢 Рассылка")
    assert "📢 Рассылать из канала: <b>Объявления</b>" in env.last_text()
    assert "покажутся по имени" not in env.last_text()
    _open_card(env)
    env.press("🧹 Фильтры")
    assert "только для источников: Склад" in env.last_text()
    assert "True" not in env.last_text() and "False" not in env.last_text()
    env.press("2.")
    assert "1. <b>Склад</b>" in env.last_text() and "🗑 1. Склад" in env.labels()


def test_keyword_patterns_are_marked_not_shown_in_their_notation(env):
    env.live.config_path.write_text(LIVE_YAML.replace(
        "        ? реклама\n", "        ? Золотой билет\n        ? r'@frmtribune'\n"), encoding="utf-8")
    _open_card(env)
    env.press("🧹 Фильтры")
    assert "слова: 🔣 @frmtribune, Золотой билет" in env.last_text()
    env.press("1.")
    text = env.last_text()
    assert "1. 🔣 <code>@frmtribune</code>" in text and "2. Золотой билет" in text and "r'" not in text
    assert "шаблон поиска" in text
    assert env.labels()[:2] == ["🗑 1. 🔣 @frmtribune", "🗑 2. Золотой билет"]


# ── ❗ Не скопировано, 🧬 Без дублей, 📈 Сводка за неделю ─────────────────────


def _failed_entry(env, link="https://t.me/c/1111111111/5", mid=5):
    from telemirror import failed
    from telemirror.outcomes import Target
    q = failed.FailedQueue(env.live.key)
    q.upsert(-1001111111111, [mid], link, [Target(-1002222222222, None, "failed", "ChatWriteForbiddenError: <нет>")])
    q.flush()
    return failed.entry_id(-1001111111111, mid)


def test_failed_posts_screen_and_retry(env):
    from telemirror import failed
    eid = _failed_entry(env)
    projects.save_chat_names(env.live.key, {-1002222222222: "Мой канал"})
    _open_card(env)
    env.press("❗ Не скопировано")
    text = env.last_text()
    assert "Ждут повтора: <b>1</b>" in text and "<b>Мой канал</b>: ChatWriteForbiddenError: &lt;нет&gt;" in text
    row = next(label for label in env.labels() if label.startswith("♻️ ") and "Мой канал" in label)
    env.press(row)
    assert failed.take_requests(env.live.key) == [eid]
    assert "Пост будет скопирован заново" in env.last_text()

    env.press("♻️ Повторить все")
    env.press("🧽 Очистить список")
    assert sorted(failed.take_requests(env.live.key)) == [failed.ALL, failed.CLEAR]


def test_the_card_shows_failed_posts_only_while_some_wait(env):
    """❗ Не скопировано is on the card only while posts wait in it, with how
    many; an empty list is still opened by the mirror's notice (after a retry)."""
    _open_card(env)
    assert not any(label.startswith("❗ Не скопировано") for label in env.labels())
    assert "Не скопировано" not in env.last_text()
    env.feed(callback_update(NavCB(s="fail", p=env.live.key).pack()))
    assert "Список пуст" in env.last_text()
    assert not any(label.startswith("♻️ Повторить все") for label in env.labels())

    _failed_entry(env)
    _open_card(env)
    assert "❗ Не скопировано (1) ›" in env.labels()
    assert "❗ Не скопировано (1)</b> —" in env.last_text()


def test_failed_posts_notice_buttons_open_the_panel(env):
    from telemirror import failed, notify
    _failed_entry(env)
    retry, screen = notify.failed_buttons(env.live.key)["inline_keyboard"][0]
    assert retry["callback_data"] == ActCB(a="fail_all", p=env.live.key).pack()
    assert screen["callback_data"] == NavCB(s="fail", p=env.live.key).pack()
    assert (retry["text"], screen["text"]) == ("♻️ Повторить все", "❗ Не скопировано")
    env.feed(callback_update(retry["callback_data"]))
    assert failed.take_requests(env.live.key) == [failed.ALL]
    env.fake.states[env.live.live_unit] = "inactive"
    env.feed(callback_update(screen["callback_data"]))
    assert "Зеркало сейчас остановлено" in env.last_text()


def test_a_stale_failed_post_row(env):
    _failed_entry(env)
    env.feed(callback_update(ActCB(a="fail_one", p=env.live.key, i=0, h="deadbeef").pack()))
    assert env.session.of(AnswerCallbackQuery)[-1].show_alert


def test_dedup_hours_parameter(env):
    _open_card(env)
    env.press("⚙️ Настройки проекта")
    assert "🧬 Без дублей: выкл" in env.labels()
    env.press("🧬 Без дублей")
    env.type("24")
    assert env.data()["dedup_hours"] == 24
    env.press("🧬 Без дублей: 24 ч")
    env.type("0")
    assert "dedup_hours" not in env.data()


def test_weekly_report_timer_switch(env):
    env.type("⚙️ Настройки")
    env.press("📈 Сводка за неделю")
    assert ["systemctl", "--no-block", "enable", "--now", "telemirror-report.timer"] in env.fake.calls

def test_a_prompt_that_failed_to_send_leaves_the_step_its_data():
    """Regression: the step's data was saved only after its prompt was sent —
    a failed send left ➕ Добавить's next step without ``source``: KeyError on
    the admin's next message."""
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey
    from aiogram.fsm.storage.memory import MemoryStorage

    from bot.routers._common import ask
    from bot.states import AddDirection

    class Msg:
        async def answer(self, *a, **kw):
            raise TelegramBadRequest(method=SimpleNamespace(), message="Bad Request")

    state = FSMContext(MemoryStorage(), StorageKey(bot_id=42, chat_id=1, user_id=1))

    async def scenario():
        with pytest.raises(TelegramBadRequest):
            await ask(Msg(), state, AddDirection.targets, "куда?", source=-100, targets=[])
        return await state.get_data()

    assert run(scenario()) == {"source": -100, "targets": []}
