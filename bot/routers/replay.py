"""⏪ История: telemirror.past for a project (``telemirror-past@<key>``) — copies
the history of the directions that have ``past_mode:``; the project's mirror
is paused meanwhile and comes back when it's over. 📜 Что копировать sets it
for every direction at once (a hand-written mix is shown as such)."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import configedit, configparse, registry, settings, status, texts
from bot.callbacks import ChoiceCB, NavCB
from bot.configstore import ConfigStore
from bot.routers import _units
from bot.keyboards.common import choice_kb
from bot.routers._common import ask, input_kind, message_of, on_action, project_of, stale_tap, start_form
from bot.runtime import Runtime
from bot.screens import open_screen, show, view
from bot.states import Input, leave_form
from bot.systemd import Systemd
from bot.texts import esc, head
from bot.writes import save
from telemirror.projects import Project

router = Router(name="replay")


def with_history(project: Project) -> int:
    return sum(1 for d in status.project_info(project).directions if d.get("past_mode"))


def delay_text(data) -> str:
    values = {settings.REPLAY_DELAY_DEFAULT if v is None else v for v in configedit.replay_delays(data)}
    if not values:
        return texts.UNKNOWN
    if len(values) > 1:
        return "разная"
    return f"{esc(values.pop())} с"


def history_summary(data) -> str:
    """What the directions copy: one choice for all, or «разное»."""
    dirs = configedit.directions(data)
    if not dirs:
        return texts.UNKNOWN
    kinds = {str(configedit.history_of(d)) for d in dirs}
    if len(kinds) > 1:
        return f"разное (у {sum(1 for d in dirs if configedit.history_of(d))} из {len(dirs)} направлений)"
    return texts.history_text(dirs[0].get("past_mode"))


def _replay(project: Project) -> NavCB:
    return NavCB(s="rpl", p=project.key)


@view("rpl")
async def replay_view(message: Message, edit: bool, nav: NavCB, *, project: Project, sysd: Systemd,
                      note: str = "", **_) -> None:
    st = await status.unit_state(sysd, project.past_unit)
    running = bool(st and st.running)
    lines = [
        f"Состояние: <b>{_units.state_text(project, project.past_unit, st)}</b>",
    ]
    if line := await _units.progress(sysd, project.past_unit, st):
        lines.append(line)
    if not sysd.available:
        lines.append(texts.SYSTEMD_UNAVAILABLE)
    info = status.project_info(project)
    hidden: tuple = ("rpl_start",) if running else ("rpl_stop",)
    if not info.writable:
        hidden += ("rpl_hist", "rpl_delay")
    elif not with_history(project):
        hidden += ("rpl_delay",)
    titles = {"rpl_hist": f"{registry.title('rpl_hist')}: {history_summary(info.data)}",
              "rpl_delay": f"{registry.title('rpl_delay')}: {delay_text(info.data)}"}
    more = ("Уже скопированные посты пропускаются; если прервать, в следующий раз продолжится с того же места. "
            "Пока идёт копирование истории, новые посты этого аккаунта не копируются — догонят после.")
    primary = "rpl_start" if not running and info.writable and with_history(project) else ""
    await show(message, edit, "rpl", project, body="\n".join(lines), more=more, note=note, hidden=hidden,
               titles=titles, pg=nav.pg, primary=primary)


@on_action(router, "rpl_delay")
async def on_delay(callback: CallbackQuery, project: Project, state: FSMContext) -> None:
    if not with_history(project):
        await stale_tap(callback, texts.config_error("no_history"))
        return
    current = delay_text(status.project_info(project).data)
    await start_form(
        callback, state, Input.value,
        f"{head(registry.title('rpl_delay'))} — сейчас: {current}.\n\nПришлите, сколько секунд ждать между "
        f"старыми постами (0–60, например <code>1.5</code>; чем больше — тем реже Telegram ограничивает "
        f"отправку), или <code>-</code>, чтобы вернуть {settings.REPLAY_DELAY_DEFAULT} с. Применится ко всем "
        "направлениям, где копируются старые посты.",
        _replay(project), data={"kind": "rpl_delay", "p": project.key},
    )


@input_kind("rpl_delay")
async def set_delay(message: Message, state: FSMContext, raw: str, data: dict, project: Project,
                    store: ConfigStore, deps: dict, **_) -> None:
    delay = None if raw == configparse.CLEAR else configparse.parse_delay(raw)
    await leave_form(message.chat.id, state)
    await save(message, False, project,
               lambda p: store.update(p, lambda cfg: configedit.set_replay_delay(cfg, delay)),
               _replay(project), deps)


@on_action(router, "rpl_start")
async def on_start(callback: CallbackQuery, project: Project, state: FSMContext, sysd: Systemd,
                   runtime: Runtime, deps: dict) -> None:
    unit = project.past_unit
    if not await _units.can_start(callback, sysd, runtime, project, unit):
        return
    if not with_history(project):
        await stale_tap(callback, texts.config_error("no_history"))
        return
    question = (f"{head(registry.title('rpl_start'))} копирование истории?\n\nСкопируются старые посты "
                f"направлений, где это выбрано. Ход виден здесь и в {registry.TASKS}.")
    if await _units.ask_start(callback, state, sysd, project, unit, question, _replay(project)) \
            and await _units.launch(callback, sysd, runtime, project, unit):
        await open_screen(_replay(project), message_of(callback), True, deps, note=_units.STARTING)


@on_action(router, "rpl_stop")
async def on_stop(callback: CallbackQuery, project: Project, state: FSMContext, sysd: Systemd) -> None:
    await _units.ask_stop(callback, state, sysd, project, project.past_unit, False, _replay(project))


# ── 📜 Что копировать: one choice for every direction ──────────────────────

HISTORY = [(registry.TITLES[k], k) for k in ("hist_none", "hist_full", "hist_last", "hist_since")]


@on_action(router, "rpl_hist")
async def on_history(callback: CallbackQuery, project: Project, state: FSMContext) -> None:
    info = status.project_info(project)
    if not info.directions:
        await stale_tap(callback, texts.config_error("no_directions"))
        return
    await start_form(
        callback, state, Input.value,
        f"{head(registry.title('rpl_hist'))} — сейчас: {history_summary(info.data)}.\n\n"
        f"Какие старые посты источников скопировать, когда вы нажмёте {head(registry.title('rpl_start'))}? "
        f"Выбор применится ко всем направлениям проекта (их {len(info.directions)}). Новые посты копируются всегда.",
        _replay(project), markup=choice_kb("rpl_hist", HISTORY, widths=(2,)),
        data={"kind": "rpl_hist", "p": project.key}, choice=True,
    )


async def _set_history(message: Message, edit: bool, state: FSMContext, project: Project, value,
                       store: ConfigStore, deps: dict) -> None:
    await leave_form(message.chat.id, state)
    await save(message, edit, project, lambda p: store.update(p, lambda cfg: configedit.set_history(cfg, value)),
               _replay(project), deps)


@router.callback_query(Input.value, ChoiceCB.filter(F.scope == "rpl_hist"))
async def on_history_pick(callback: CallbackQuery, callback_data: ChoiceCB, state: FSMContext,
                          store: ConfigStore, deps: dict) -> None:
    data = await state.get_data()
    if data.get("kind") != "rpl_hist" or callback_data.value not in {k for _, k in HISTORY}:
        await stale_tap(callback)
        return
    if (project := await project_of(callback, data["p"])) is None:
        return
    await callback.answer()
    if callback_data.value in ("hist_last", "hist_since"):
        kind = "rpl_last" if callback_data.value == "hist_last" else "rpl_since"
        ask_text = ("пришлите, сколько последних постов каждого источника скопировать (1–1000000):"
                    if kind == "rpl_last" else
                    "пришлите дату, с которой копировать: <code>2024-01-31</code> или <code>2024-01-31T12:00:00</code>:")
        await message_of(callback).edit_reply_markup(reply_markup=None)
        await ask(message_of(callback), state, Input.value, f"{head(registry.title('rpl_hist'))} — {ask_text}",
                  kind=kind)
        return
    value = None if callback_data.value == "hist_none" else {"full_history": True}
    await _set_history(message_of(callback), True, state, project, value, store, deps)


@input_kind("rpl_hist")
async def history_typed(message: Message, **_) -> None:
    await message.answer(texts.USE_BUTTONS)


@input_kind("rpl_last")
@input_kind("rpl_since")
async def set_history(message: Message, state: FSMContext, raw: str, data: dict, project: Project,
                      store: ConfigStore, deps: dict, **_) -> None:
    value = ({"last_n": configparse.parse_last_n(raw)} if data["kind"] == "rpl_last"
             else {"since_date": configparse.parse_since(raw)})
    await _set_history(message, False, state, project, value, store, deps)
