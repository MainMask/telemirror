"""Panel handlers end-to-end through the real Dispatcher (fake Bot API session,
fake systemd, config files in tmp): access control, the start screen, in-place
navigation, config writes and service control."""

import pytest
import yaml
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import (
    AnswerCallbackQuery,
    EditMessageText,
    SendMessage,
)
from aiogram.types import ReplyKeyboardMarkup

from telemirror.panel import configstore, settings, texts
from telemirror.panel.app import build_dispatcher
from telemirror.panel.callbacks import Act, Nav
from telemirror.panel.configstore import ConfigStore
from telemirror.panel.middlewares import AdminOnly
from telemirror.panel.routers import maintenance
from telemirror.panel.runtime import Launch, Runtime
from telemirror.panel.settings import Project
from telemirror.panel.systemd import Systemd, parse_show
from telemirror.panel.ui import Panel
from tests._panel import (
    ADMIN_ID,
    SHOW,
    STRANGER_ID,
    FakeSystemd,
    callback_update,
    make_bot,
    message_update,
)
from tests.conftest import run

LIVE_YAML = """\
# live mirror — hand-written comment
disable_edit: true
directions:
  - from: [-1001111111111]
    to: [-1002222222222]
"""
COURSES_YAML = "directions:\n- from:\n  - '-1003333333333#1'\n  to:\n  - '-1004444444444#5'\n  past_mode:\n    full_history: true\n"


async def _ok(_project, _text):
    return None


_DP: list = []


def _dispatcher():
    if not _DP:
        _DP.append(build_dispatcher(frozenset({ADMIN_ID})))
    return _DP[0]


@pytest.fixture
def env(tmp_path, monkeypatch):
    live = Project("live", tmp_path / "mirror.config.yml", "live", "file", live=True)
    crs = Project("crs", tmp_path / "citadel_courses.config.yml", "crs", "env", live=False)
    live.path.write_text(LIVE_YAML, encoding="utf-8")
    crs.path.write_text(COURSES_YAML, encoding="utf-8")
    monkeypatch.setattr(settings, "PROJECTS", (live, crs))
    monkeypatch.setattr(settings, "YAML_CONFIG_ENV_SET", False)
    monkeypatch.setattr(settings, "TASK_ENV_DIR", tmp_path / "run")
    fake = FakeSystemd({settings.LIVE_UNIT: "active"})
    dp = _dispatcher()
    # Routers are module singletons (attachable once) — one Dispatcher for the
    # module, fresh per-test state injected here.
    dp["sysd"] = Systemd(runner=fake)
    dp["store"] = ConfigStore(validator=_ok)
    dp["panel"] = Panel()
    dp["runtime"] = Runtime()
    dp.fsm.storage = MemoryStorage()
    bot, session = make_bot()

    class Env:
        pass

    e = Env()
    e.dp, e.bot, e.session, e.fake, e.live, e.crs = dp, bot, session, fake, live, crs
    e.feed = lambda update: run(dp.feed_update(bot, update))
    return e


# ── access ──────────────────────────────────────────────────────────────────


def test_admin_only_requires_admins():
    with pytest.raises(ValueError):
        AdminOnly(frozenset())


def test_stranger_gets_nothing(env):
    env.feed(message_update("/start", uid=STRANGER_ID))
    env.feed(callback_update(Nav(s="prj").pack(), uid=STRANGER_ID))
    env.feed(callback_update(Act(a="rst", p="live", ok=True).pack(), uid=STRANGER_ID))
    assert env.session.requests == []
    assert env.fake.calls == []  # no systemctl call either


# ── start screen ────────────────────────────────────────────────────────────


def test_start_screen(env):
    env.feed(message_update("/start"))
    sent = env.session.of(SendMessage)
    assert len(sent) == 1
    text = sent[0].text
    assert "👋 Здравствуйте, <b>Даниил &lt;b&gt;</b>!" in text  # name is HTML-escaped
    assert "📁 Проектов: <b>2</b> · 🔀 направлений: <b>2</b> · 🟢 зеркало: <b>работает</b>" in text
    for section in ("📁 <b>Проекты</b> —", "📊 <b>Задачи</b> —", "⚙️ <b>Настройки</b> —"):
        assert section in text
    assert "/status — что сейчас выполняется · /cancel — выйти из ввода или остановить задачу" in text
    assert text.endswith("<i>Выберите раздел в меню ниже</i> 👇")
    kb = sent[0].reply_markup
    assert isinstance(kb, ReplyKeyboardMarkup) and kb.is_persistent and kb.resize_keyboard
    assert [b.text for b in kb.keyboard[0]] == [texts.BTN_PROJECTS, texts.BTN_TASKS, texts.BTN_SETTINGS]


def test_reply_button_replaces_panel_message(env):
    env.feed(message_update(texts.BTN_PROJECTS))
    env.feed(message_update(texts.BTN_TASKS))
    sent = env.session.of(SendMessage)
    assert len(sent) == 2
    assert texts.PROJECT_TITLES["live"] in str(sent[0].reply_markup)
    assert "📊 <b>Задачи</b>" in sent[1].text


# ── callbacks: in place, always answered, ≤64 bytes ─────────────────────────


def test_navigation_edits_in_place_and_answers(env):
    for data in (Nav(s="prj"), Nav(s="pc", p="live"), Nav(s="dl", p="live"), Nav(s="dc", p="live", i=0),
                 Nav(s="flt", p="live"), Nav(s="par", p="crs"), Nav(s="tsk"), Nav(s="uc", p="crs"),
                 Nav(s="set"), Nav(s="mnt"), Nav(s="rs"), Nav(s="sp")):
        env.feed(callback_update(data.pack()))
    assert env.session.of(SendMessage) == []
    edits = env.session.of(EditMessageText)
    assert len(edits) == 12 and all(e.message_id == 77 for e in edits)
    assert len(env.session.of(AnswerCallbackQuery)) == 12
    assert "-1001111111111" in edits[3].text  # direction card
    assert "line &lt;two&gt;" in edits[7].text  # journal is escaped


def test_message_not_modified_is_swallowed():
    bot, session = make_bot()

    async def boom(_bot, method, timeout=None):
        raise TelegramBadRequest(method=method, message="Bad Request: message is not modified")

    session.make_request = boom  # type: ignore[method-assign]
    run(Panel().edit(bot, ADMIN_ID, "same", None, message_id=5))  # no exception, no resend


def test_callback_data_fits_64_bytes():
    worst = [
        Nav(s="dc", p="live", pg=10**6, i=10**6),
        Act(a="dd", p="live", pg=10**6, i=10**6, h="ffffffff", ok=True),
        Act(a="spf", p="sp", i=3),
    ]
    for cb in worst:
        packed = cb.pack()
        assert len(packed.encode()) <= 64
        assert type(cb).unpack(packed) == cb


# ── config writes ───────────────────────────────────────────────────────────


def test_add_direction_flow(env):
    env.feed(callback_update(Act(a="add", p="live").pack()))
    env.feed(message_update("not an id"))
    assert "Неверный ID канала" in env.session.last_text()
    env.feed(message_update("-1005555555555"))
    env.feed(message_update("-1006666666666#3, -1007777777777"))
    env.feed(callback_update(Act(a="am", p="live", i=0).pack()))
    env.feed(callback_update(Act(a="ah", p="live", i=1).pack()))
    assert "Проверьте направление" in env.session.last_text()
    env.feed(callback_update(Act(a="as", p="live").pack()))

    text = env.live.path.read_text(encoding="utf-8")
    assert text.startswith("# live mirror — hand-written comment\n")
    assert yaml.safe_load(text)["directions"][-1] == {
        "from": [-1005555555555],
        "to": ["-1006666666666#3", -1007777777777],
        "past_mode": {"full_history": True},
    }
    assert "всего 2" in env.session.last_text()
    # typed inputs are deleted to keep a single panel message
    assert env.session.of(SendMessage) == []


def test_courses_direction_always_gets_history(env):
    env.feed(callback_update(Act(a="add", p="crs").pack()))
    env.feed(message_update("-1008888888888"))
    env.feed(message_update("-1009999999999"))
    env.feed(callback_update(Act(a="am", p="crs", i=0).pack()))
    env.feed(callback_update(Act(a="as", p="crs").pack()))
    added = yaml.safe_load(env.crs.path.read_text(encoding="utf-8"))["directions"][-1]
    assert added["past_mode"] == {"full_history": True}


def test_cancel_leaves_input_mode(env):
    env.feed(callback_update(Act(a="add", p="live").pack()))
    env.feed(message_update("/cancel"))
    assert env.session.last_text() == texts.CANCEL_INPUT
    env.feed(message_update("-1005555555555"))  # no longer treated as input
    assert env.live.path.read_text(encoding="utf-8") == LIVE_YAML


def test_delete_direction_needs_confirmation(env):
    fp = configstore.fingerprint(configstore.directions(configstore.load(env.live).data)[0])
    env.feed(callback_update(Act(a="dd", p="live", i=0, h=fp).pack()))
    assert "Удалить направление 1?" in env.session.last_text()
    assert env.live.path.read_text(encoding="utf-8") == LIVE_YAML
    env.feed(callback_update(Act(a="dd", p="live", i=0, h=fp, ok=True).pack()))
    assert yaml.safe_load(env.live.path.read_text(encoding="utf-8"))["directions"] == []
    # a stale fingerprint is refused
    env.feed(callback_update(Act(a="dd", p="live", i=0, h=fp, ok=True).pack()))
    assert "Список направлений изменился" in env.session.last_text()


def test_toggle_global_param(env):
    env.feed(callback_update(Act(a="ge", p="live").pack()))
    assert yaml.safe_load(env.live.path.read_text(encoding="utf-8"))["disable_edit"] is False
    answers = env.session.of(AnswerCallbackQuery)
    assert answers[-1].text == texts.SAVED["live"]


def test_read_only_when_yaml_config_env(env, monkeypatch):
    monkeypatch.setattr(settings, "YAML_CONFIG_ENV_SET", True)
    env.feed(callback_update(Nav(s="pc", p="live").pack()))
    assert "YAML_CONFIG_ENV" in env.session.last_text()
    env.feed(callback_update(Act(a="add", p="live").pack()))
    assert env.session.of(AnswerCallbackQuery)[-1].show_alert


# ── services ────────────────────────────────────────────────────────────────


def test_restart_confirm_then_cooldown(env):
    env.feed(callback_update(Act(a="rst", p="live").pack()))
    assert "Перезапустить живое зеркало?" in env.session.last_text()
    assert not any("restart" in c for c in env.fake.calls)
    env.feed(callback_update(Act(a="rst", p="live", ok=True).pack()))
    assert ["systemctl", "--no-block", "restart", settings.LIVE_UNIT] in env.fake.calls
    env.feed(callback_update(Act(a="rst", p="live", ok=True).pack()))
    assert sum(c[:3] == ["systemctl", "--no-block", "restart"] for c in env.fake.calls) == 1
    assert "Подождите" in env.session.of(AnswerCallbackQuery)[-1].text


def test_stopping_a_task_brings_the_mirror_back(env):
    env.fake.states[settings.COURSES_UNIT] = "active"
    env.feed(message_update("/cancel"))
    assert env.session.last_text() == texts.CANCEL_PICK
    env.feed(callback_update(Act(a="stop", p="crs", ok=True).pack()))
    assert ["systemctl", "--no-block", "stop", settings.COURSES_UNIT] in env.fake.calls
    assert ["systemctl", "--no-block", "start", settings.LIVE_UNIT] in env.fake.calls


def test_courses_start_refused_while_a_task_runs(env):
    env.fake.states[settings.UNITS["sp"]] = "active"
    env.feed(callback_update(Act(a="start", p="crs").pack()))
    assert "Уже выполняется" in env.session.of(AnswerCallbackQuery)[-1].text


# ── maintenance ─────────────────────────────────────────────────────────────


def test_build_task_args_whitelist():
    assert maintenance.build_task_args("rs", True) == ["--dry-run"]
    assert maintenance.build_task_args("rs", False) == ["--yes"]
    assert maintenance.build_task_args("sp", True, frozenset({"--thorough", "--additive"})) == [
        "--additive", "--thorough", "--dry-run",
    ]
    assert maintenance.build_task_args("sp", False) == []
    with pytest.raises(ValueError):
        maintenance.build_task_args("sp", True, frozenset({"--only"}))
    with pytest.raises(ValueError):
        maintenance.build_task_args("rs", True, frozenset({"--additive"}))
    with pytest.raises(ValueError):
        maintenance.build_task_args("clear_channels", True)


def test_real_run_only_after_successful_matching_dry_run():
    rt = Runtime()
    done = parse_show(SHOW.format(active="inactive", sub="dead", result="success"))  # since 1763390000
    assert not maintenance.can_run_real("sp", rt, done)
    rt.launches["sp"] = Launch(("--dry-run",), True, 1763380000.0)
    assert maintenance.can_run_real("sp", rt, done)
    rt.sp_flags.add("--additive")  # flags changed since the dry-run
    assert not maintenance.can_run_real("sp", rt, done)
    rt.sp_flags.clear()
    failed = parse_show(SHOW.format(active="failed", sub="failed", result="exit-code"))
    assert not maintenance.can_run_real("sp", rt, failed)
    rt.launches["sp"] = Launch(("--dry-run",), True, 1763395000.0)  # launched after it ended
    assert not maintenance.can_run_real("sp", rt, done)


def test_dry_run_launch_writes_env_file(env, tmp_path):
    env.feed(callback_update(Act(a="spf", p="sp", i=0).pack()))  # --additive
    env.feed(callback_update(Act(a="run", p="sp", i=0).pack()))
    assert "проверка" in env.session.last_text()
    env.feed(callback_update(Act(a="run", p="sp", i=0, ok=True).pack()))
    assert (tmp_path / "run" / "sync_pins.env").read_text() == "TASK_ARGS=--additive --dry-run\n"
    assert ["systemctl", "--no-block", "start", "telemirror-task@sync_pins.service"] in env.fake.calls
    # the real run is refused until that dry-run has finished successfully
    env.feed(callback_update(Act(a="run", p="sp", i=1, ok=True).pack()))
    assert env.session.of(AnswerCallbackQuery)[-1].text == texts.RUN_NEEDS_DRY
