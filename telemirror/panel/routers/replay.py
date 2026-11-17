"""⏪ Догрузка: past_mode.py for a project (``telemirror-past@<key>``) — copies
the history of the directions that have ``past_mode:``; the project's mirror
is paused meanwhile and comes back when it's over."""

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from telemirror.panel import configstore, registry, status, texts
from telemirror.panel.callbacks import ActCB, NavCB
from telemirror.panel.configstore import ConfigError, ConfigStore
from telemirror.panel.routers._common import (
    ask_confirm,
    confirmed,
    input_kind,
    leave_form,
    message_of,
    on_action,
    project_of,
    session_ok,
    stale_tap,
    start_form,
)
from telemirror.panel.routers.projects import do_start, pause_text
from telemirror.panel.routers.tasks import progress, state_text
from telemirror.panel.runtime import Runtime
from telemirror.panel.screens import esc, head, show, view
from telemirror.panel.states import Input
from telemirror.panel.systemd import Systemd, SystemdError
from telemirror.panel.writes import save
from telemirror.projects import Project

router = Router(name="replay")


@view("rpl")
async def replay_view(message: Message, edit: bool, nav: NavCB, state: FSMContext, sysd: Systemd,
                      note: str = "", **_) -> None:
    project = status.find(nav.p)
    if project is None:
        await message.answer(texts.NO_PROJECT)
        return
    await show_replay(message, edit, project, sysd, note)


def with_history(project: Project) -> int:
    return sum(1 for d in status.project_info(project).directions if d.get("past_mode"))


DEFAULT_REPLAY_DELAY = 0.5  # config.PastModeConfig.send_delay


def delay_text(data) -> str:
    values = {DEFAULT_REPLAY_DELAY if v is None else v for v in configstore.replay_delays(data)}
    if not values:
        return "—"
    if len(values) > 1:
        return "разная"
    return f"{esc(values.pop())} с"


async def show_replay(message: Message, edit: bool, project: Project, sysd: Systemd, note: str = "") -> None:
    st = await status.unit_state(sysd, project.past_unit)
    running = bool(st and st.running)
    lines = [
        f"Состояние: <b>{state_text(project, project.past_unit, st)}</b>",
        f"Направлений с историей: <b>{with_history(project)}</b> — задаётся в карточке "
        f"направления: {registry.title('dir_hist')}.",
        "Уже переданные сообщения пропускаются; прерванная догрузка продолжается с того же места.",
    ]
    if line := await progress(sysd, project.past_unit, st):
        lines.append(line)
    if not sysd.available:
        lines.append(texts.SYSTEMD_UNAVAILABLE)
    info = status.project_info(project)
    hidden: tuple = ("rpl_start",) if running else ("rpl_stop",)
    if not info.writable:
        hidden += ("rpl_delay",)
    titles = {"rpl_delay": f"{registry.title('rpl_delay')}: {delay_text(info.data)}"}
    await show(message, edit, "rpl", project, body="\n".join(lines), note=note, hidden=hidden, titles=titles)


@on_action(router, "rpl_delay")
async def on_delay(callback: CallbackQuery, callback_data: ActCB, state: FSMContext) -> None:
    project = await project_of(callback, callback_data.p)
    if project is None:
        return
    if not with_history(project):
        await stale_tap(callback, f"⛔ Ни у одного направления не задана история: {registry.menu_path('dir_hist')}.")
        return
    current = delay_text(status.project_info(project).data)
    await start_form(
        callback, state, Input.value,
        f"{head(registry.title('rpl_delay'))} — сейчас: {current}.\n\nПришлите число секунд между "
        f"отправками при догрузке (0–60, например <code>1.5</code>; больше — реже FloodWait) или "
        f"<code>-</code>, чтобы вернуть {DEFAULT_REPLAY_DELAY} с. Применится ко всем направлениям с историей.",
        NavCB(s="rpl", p=project.key), data={"kind": "rpl_delay", "p": project.key},
    )


@input_kind("rpl_delay")
async def set_delay(message: Message, state: FSMContext, raw: str, data: dict, store: ConfigStore,
                    sysd: Systemd, **_) -> None:
    try:
        delay = None if raw == configstore.CLEAR else configstore.parse_delay(raw)
    except ConfigError as e:
        await message.answer(f"{texts.config_error(e.code, e.detail)}\nПришлите ещё раз:")
        return
    project = status.find(data["p"])
    await leave_form(message.chat.id, state)
    if project is None:
        await message.answer(texts.NO_PROJECT)
        return

    async def after(target: Message, done: str) -> None:
        await show_replay(target, True, project, sysd, done)

    await save(message, False, project,
               lambda p: store.update(p, lambda cfg: configstore.set_replay_delay(cfg, delay)),
               after, NavCB(s="rpl", p=project.key), sysd)


@on_action(router, "rpl_start")
async def on_start(callback: CallbackQuery, callback_data: ActCB, state: FSMContext, sysd: Systemd,
                   runtime: Runtime) -> None:
    project = await project_of(callback, callback_data.p)
    if project is None:
        return
    if not sysd.available:
        await stale_tap(callback, texts.SYSTEMD_UNAVAILABLE)
        return
    if not await session_ok(callback, project):
        return
    if not with_history(project):
        await stale_tap(callback, f"⛔ Ни у одного направления не задана история: {registry.menu_path('dir_hist')}.")
        return
    if left := runtime.cooldown_left(project.past_unit):
        await stale_tap(callback, texts.COOLDOWN.format(sec=left))
        return
    holders = [(p, u) for p, u in await status.session_holders(sysd, project) if u != project.past_unit]
    await ask_confirm(
        callback, state,
        f"{head('▶️ Начать догрузку')}?\n\nКопируется история направлений, у которых она задана. "
        f"Ход виден здесь и в {registry.TASKS}.{pause_text(holders)}",
        "rpl_start", NavCB(s="rpl", p=project.key), p=project.key,
    )


@confirmed("rpl_start")
async def do_confirmed_start(callback: CallbackQuery, action: dict, state: FSMContext, sysd: Systemd,
                             runtime: Runtime, **_) -> None:
    project = await project_of(callback, action["p"])
    if project is not None and await do_start(callback, sysd, runtime, project, project.past_unit):
        await show_replay(message_of(callback), True, project, sysd, "▶️ Догрузка запускается.")


@on_action(router, "rpl_stop")
async def on_stop(callback: CallbackQuery, callback_data: ActCB, state: FSMContext) -> None:
    project = await project_of(callback, callback_data.p)
    if project is None:
        return
    await ask_confirm(
        callback, state,
        f"{head('⏹ Прервать догрузку')}?\n\nВ следующий раз она продолжится с того же места; "
        "приостановленные зеркала запустятся снова.",
        "rpl_stop", NavCB(s="rpl", p=project.key), p=project.key,
    )


@confirmed("rpl_stop")
async def do_stop(callback: CallbackQuery, action: dict, state: FSMContext, sysd: Systemd, **_) -> None:
    project = await project_of(callback, action["p"])
    if project is None:
        return
    try:
        await sysd.stop(project.past_unit)
    except SystemdError as e:
        await stale_tap(callback, texts.SYSTEMD_ERROR.format(detail=str(e)[:150]))
        return
    await callback.answer("Команда отправлена systemd.")
    await show_replay(message_of(callback), True, project, sysd, "⏹ Догрузка прерывается.")
