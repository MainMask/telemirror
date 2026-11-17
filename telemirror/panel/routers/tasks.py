"""📊 Задачи: every project's units (mirror, history replay, maintenance) and a
unit's card with its journal; ▶️ / ⏹ / 🔁 there."""

import time
from typing import Optional

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from telemirror.panel import settings, status, texts, turns
from telemirror.panel.callbacks import ActCB, NavCB
from telemirror.panel.keyboards.common import button
from telemirror.panel.routers._common import (
    ask_confirm,
    confirmed,
    message_of,
    on_action,
    project_of,
    session_ok,
    stale_tap,
)
from telemirror.panel.routers.projects import do_start, pause_text, restart_pause_text
from telemirror.panel.runtime import Runtime
from telemirror.panel.screens import esc, head, show, view
from telemirror.panel.systemd import Systemd, SystemdError, UnitState
from telemirror.panel.watcher import unit_label
from telemirror.projects import Project, list_projects

router = Router(name="tasks")

_PROGRESS_GREP = r"\[Progress\]|\[PastMode\]"


def _mask(text: str) -> str:
    return text.replace(settings.BOT_TOKEN, "***") if settings.BOT_TOKEN else text


def state_text(project: Project, unit: str, st: Optional[UnitState]) -> str:
    active = st.active if st else None
    state = texts.mirror_state(active) if unit == project.live_unit else texts.task_state(active)
    return f"{texts.state_icon(active)} {state}"


async def progress(sysd: Systemd, unit: str, st: Optional[UnitState]) -> str:
    """The last past_mode progress line of the current replay run, verbatim."""
    if st is None or not st.running or not st.invocation:
        return ""
    try:
        line = await sysd.journal(unit, 1, st.invocation, _PROGRESS_GREP)
    except SystemdError:
        return ""
    return f"<b>Ход:</b> <code>{esc(_mask(line))}</code>" if line else ""


@view("tsk")
async def tasks_view(message: Message, edit: bool, nav: NavCB, state: FSMContext, sysd: Systemd,
                     note: str = "", **_) -> None:
    if not sysd.available:
        await show(message, edit, "tsk", body=texts.SYSTEMD_UNAVAILABLE, note=note)
        return
    lines, own = [], []
    for p in list_projects():
        for kind, unit in enumerate(p.units):
            st = await status.unit_state(sysd, unit)
            # a replay / a task only while it runs or after a failure — the mirror always
            if unit != p.live_unit and not (st and (st.running or st.active == "failed")):
                continue
            label = f"{unit_label(p, unit)} — {state_text(p, unit, st)}"
            lines.append(esc(label) + ("\n" + await progress(sysd, unit, st) if unit == p.past_unit else ""))
            own.append([button(label[:60], NavCB(s="unit", p=p.key, i=kind))])
    body = "\n".join(lines) if lines else "Проектов нет — нечего показывать."
    await show(message, edit, "tsk", body=body, note=note, own=own)


@view("unit")
async def unit_view(message: Message, edit: bool, nav: NavCB, state: FSMContext, sysd: Systemd,
                    note: str = "", **_) -> None:
    project = status.find(nav.p)
    if project is None or not 0 <= nav.i < len(project.units):
        await tasks_view(message, edit, NavCB(s="tsk"), state, sysd, note=texts.NO_PROJECT)
        return
    await show_unit(message, edit, project, nav.i, sysd, note)


async def show_unit(message: Message, edit: bool, project: Project, kind: int, sysd: Systemd,
                    note: str = "") -> None:
    unit = project.units[kind]
    st = await status.unit_state(sysd, unit)
    lines = [f"<b>{esc(unit_label(project, unit))}</b> · <code>{esc(unit)}</code>",
             f"Состояние: <b>{state_text(project, unit, st)}</b>" + (f" ({esc(st.sub)})" if st and st.sub else "")]
    journal = ""
    if st is not None:
        if st.since:
            lines.append(f"С {texts.fmt_ts(st.since)} ({texts.fmt_duration(time.time() - st.since)})")
        if unit == project.live_unit and st.restarts:
            lines.append(f"Перезапусков systemd: {st.restarts}")
        if st.running and st.memory:
            lines.append(f"Память: {texts.fmt_bytes(st.memory)}")
        if st.active == "failed" or (not st.running and st.result not in ("", "success")):
            lines.append(f"Результат последнего запуска: <b>{esc(st.result)}</b>")
        if unit == project.past_unit and (line := await progress(sysd, unit, st)):
            lines.append(line)
        try:
            raw = await sysd.journal(unit, settings.JOURNAL_LINES, st.invocation)
        except SystemdError as e:
            raw = str(e)
        raw = _mask(raw)[-settings.JOURNAL_MAX_CHARS:]
        journal = (f"<b>Журнал последнего запуска</b> (до {settings.JOURNAL_LINES} строк):\n<pre>{esc(raw)}</pre>"
                   if raw else "<i>Журнал пуст.</i>")
    if not sysd.available:
        lines.append(texts.SYSTEMD_UNAVAILABLE)
    running = bool(st and st.running)
    # the mirror: ▶️ or ⏹ + 🔁; a replay / a task starts from its own screen, ⏹ while it runs
    shown: set = set()
    if sysd.available and unit == project.live_unit:
        shown = {"u_stop", "u_restart"} if running else {"u_start"}
    elif sysd.available and running:
        shown = {"u_stop"}
    hidden = tuple(a for a in ("u_start", "u_stop", "u_restart") if a not in shown)
    body = "\n".join(lines) + ("\n\n" + journal if journal else "")
    await show(message, edit, "unit", project, body=body, note=note, hidden=hidden, i=kind)


@on_action(router, "u_start")
async def on_start(callback: CallbackQuery, callback_data: ActCB, state: FSMContext, sysd: Systemd,
                   runtime: Runtime) -> None:
    project = await project_of(callback, callback_data.p)
    if project is None or callback_data.i != 0:
        await stale_tap(callback)
        return
    if not await session_ok(callback, project):
        return
    if not project.config_path.exists():  # config.py refuses to start without it
        await stale_tap(callback, texts.READ_ONLY["missing"])
        return
    unit = project.live_unit
    if left := runtime.cooldown_left(unit):
        await stale_tap(callback, texts.COOLDOWN.format(sec=left))
        return
    holders = [(p, u) for p, u in await status.session_holders(sysd, project) if u != unit]
    if holders:
        await ask_confirm(callback, state, f"{head('▶️ Запустить зеркало')}?{pause_text(holders, True)}", "u_start",
                          NavCB(s="unit", p=project.key, i=0), p=project.key)
        return
    if await do_start(callback, sysd, runtime, project, unit):
        await show_unit(message_of(callback), True, project, 0, sysd, "▶️ Запускается.")


@confirmed("u_start")
async def do_confirmed_start(callback: CallbackQuery, action: dict, state: FSMContext, sysd: Systemd,
                             runtime: Runtime, **_) -> None:
    project = await project_of(callback, action["p"])
    if project is not None and await do_start(callback, sysd, runtime, project, project.live_unit):
        await show_unit(message_of(callback), True, project, 0, sysd, "▶️ Запускается.")


@on_action(router, "u_stop", "u_restart")
async def on_stop(callback: CallbackQuery, callback_data: ActCB, state: FSMContext, sysd: Systemd) -> None:
    project = await project_of(callback, callback_data.p)
    if project is None or not 0 <= callback_data.i < len(project.units):
        return
    unit = project.units[callback_data.i]
    stop = callback_data.a == "u_stop"
    what = "⏹ Остановить" if stop else "🔁 Перезапустить"
    note = ""
    if stop and unit == project.past_unit:
        note = "\n\nДогрузка продолжится с того же места при следующем запуске."
    if stop and unit != project.live_unit:
        note += "\nЗеркала, приостановленные ради неё, запустятся снова."
    if not stop and unit == project.live_unit:
        note += await restart_pause_text(sysd, project)
    await ask_confirm(callback, state, f"{head(what)} «{esc(unit_label(project, unit))}»?{note}",
                      callback_data.a, NavCB(s="unit", p=project.key, i=callback_data.i),
                      p=project.key, i=callback_data.i)


@confirmed("u_stop")
@confirmed("u_restart")
async def do_stop(callback: CallbackQuery, action: dict, state: FSMContext, sysd: Systemd,
                  runtime: Runtime, **_) -> None:
    project = await project_of(callback, action["p"])
    if project is None:
        return
    unit = project.units[action["i"]]
    restart = action["kind"] == "u_restart"
    if restart and (left := runtime.cooldown_left(unit)):
        await stale_tap(callback, texts.COOLDOWN.format(sec=left))
        return
    try:
        if restart:
            await turns.start(sysd, runtime, project, unit, restart=True)
        elif unit == project.live_unit:
            await sysd.disable(unit)  # turned off for good, not on the next boot either
        else:
            await sysd.stop(unit)
    except SystemdError as e:
        await stale_tap(callback, texts.SYSTEMD_ERROR.format(detail=str(e)[:150]))
        return
    await callback.answer("Команда отправлена systemd.")
    await show_unit(message_of(callback), True, project, action["i"], sysd,
                    "🔁 Перезапускается." if restart else "⏹ Останавливается.")
