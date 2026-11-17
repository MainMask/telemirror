"""📊 Задачи: unit states, unit cards with the journal, start/stop/restart."""

import logging
import time
from typing import Optional

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup
from aiogram.utils.callback_answer import CallbackAnswer

from telemirror.panel import keyboards, settings, status, texts
from telemirror.panel.callbacks import Act, Nav
from telemirror.panel.runtime import Runtime
from telemirror.panel.systemd import Systemd, SystemdError, UnitState
from telemirror.panel.ui import Panel, Screen, show

logger = logging.getLogger(__name__)
router = Router(name="tasks")

_PROGRESS_GREP = r"\[Progress\]|\[PastMode\]"


def _title(key: str) -> str:
    return texts.UNIT_TITLES[key]


def _mask(text: str) -> str:
    return text.replace(settings.BOT_TOKEN, "***") if settings.BOT_TOKEN else text


async def _progress(sysd: Systemd, st: Optional[UnitState]) -> str:
    """Last past_mode progress line of the current replay run, verbatim."""
    if st is None or not st.running or not st.invocation:
        return ""
    try:
        line = await sysd.journal(settings.COURSES_UNIT, 1, st.invocation, _PROGRESS_GREP)
    except SystemdError:
        return ""
    return texts.UNIT_PROGRESS.format(line=texts.esc(_mask(line))) if line else ""


async def tasks_screen(sysd: Systemd) -> Screen:
    if not sysd.available:
        return (
            f"{texts.TASKS_TITLE}\n\n{texts.SYSTEMD_UNAVAILABLE}",
            keyboards.back(Nav(s="tsk"), texts.BTN_REFRESH),
        )
    lines, items = [], []
    for key in settings.UNITS:
        st = await status.unit_state(sysd, key)
        label = texts.unit_line(_title(key), st.active if st else None, key == "live")
        lines.append(label)
        if key == "crs":
            lines[-1] += await _progress(sysd, st)
        items.append((key, label))
    return f"{texts.TASKS_TITLE}\n\n" + "\n".join(lines), keyboards.tasks_list(items)


async def unit_screen(sysd: Systemd, key: str) -> Screen:
    st = await status.unit_state(sysd, key)
    live = key == "live"
    active = st.active if st else None
    sub = f" ({texts.esc(st.sub)})" if st and st.sub else ""
    since = ""
    extra = ""
    journal = ""
    if st is not None:
        if st.since:
            since = texts.UNIT_SINCE.format(
                when=texts.fmt_ts(st.since), ago=texts.fmt_duration(time.time() - st.since)
            )
        if live and st.restarts:
            extra += texts.UNIT_RESTARTS.format(n=st.restarts)
        if st.running and st.memory:
            extra += texts.UNIT_MEMORY.format(mem=texts.fmt_bytes(st.memory))
        if st.active == "failed" or (not st.running and st.result not in ("", "success")):
            extra += texts.UNIT_RESULT_FAILED.format(result=texts.esc(st.result))
        if key == "crs":
            extra += await _progress(sysd, st)
        try:
            raw = await sysd.journal(settings.UNITS[key], settings.JOURNAL_LINES, st.invocation)
        except SystemdError as e:
            raw = str(e)
        raw = _mask(raw)[-settings.JOURNAL_MAX_CHARS:]
        journal = (
            texts.UNIT_JOURNAL.format(n=settings.JOURNAL_LINES, journal=texts.esc(raw))
            if raw
            else texts.UNIT_JOURNAL_EMPTY
        )
    state = texts.mirror_state(active) if live else texts.task_state(active)
    text = texts.UNIT_CARD.format(
        icon=texts.state_icon(active), title=_title(key), state=state, sub=sub,
        since=since, extra=extra,
    )
    if not sysd.available:
        text += "\n\n" + texts.SYSTEMD_UNAVAILABLE
    return text + journal, keyboards.unit_card(key, bool(st and st.running), sysd.available)


@router.callback_query(Nav.filter(F.s == "tsk"))
async def on_tasks(callback: CallbackQuery, bot: Bot, panel: Panel, sysd: Systemd) -> None:
    await show(callback, bot, panel, await tasks_screen(sysd))


@router.callback_query(Nav.filter(F.s == "uc"), Nav.filter(F.p.in_(settings.UNITS)))
async def on_unit(
    callback: CallbackQuery, callback_data: Nav, bot: Bot, panel: Panel, sysd: Systemd
) -> None:
    await show(callback, bot, panel, await unit_screen(sysd, callback_data.p))


# ── start / stop / restart ──────────────────────────────────────────────────


def _no_button(data: Act) -> Nav:
    # h="pc": the action came from a project card (project key == unit key) —
    # "No" returns there instead of the unit card.
    return Nav(s="pc", p=data.p) if data.h == "pc" else Nav(s="uc", p=data.p)


def _confirm(text: str, data: Act) -> Screen:
    yes = Act(a=data.a, p=data.p, h=data.h, ok=True)
    return text, keyboards.confirm(yes, _no_button(data))


async def _busy_text(sysd: Systemd) -> Optional[str]:
    running = await status.running_exclusive(sysd)
    return texts.TASK_BUSY.format(title=_title(running[0])) if running else None


async def _perform(
    callback: CallbackQuery, callback_answer: CallbackAnswer, bot: Bot, panel: Panel,
    sysd: Systemd, runtime: Runtime, data: Act,
) -> None:
    key = data.p
    try:
        if data.a in ("start", "rst"):
            left = runtime.cooldown_left(key)
            if left:
                callback_answer.text = texts.COOLDOWN.format(sec=left)
                callback_answer.show_alert = True
                return
            if data.a == "rst":
                await sysd.restart(settings.UNITS[key])
            else:
                await sysd.start(settings.UNITS[key])
            runtime.mark_started(key)
        else:  # stop
            await sysd.stop(settings.UNITS[key])
            if key in settings.EXCLUSIVE_UNIT_KEYS:
                # The task held the session instead of the mirror — bring it back.
                await sysd.start(settings.LIVE_UNIT)
    except SystemdError as e:
        logger.error("panel: %s %s failed: %s", data.a, settings.UNITS[key], e)
        callback_answer.text = texts.SYSTEMD_ERROR.format(detail=str(e)[:150])
        callback_answer.show_alert = True
        return
    logger.info("panel: %s %s by admin %s", data.a, settings.UNITS[key], callback.from_user.id)
    callback_answer.text = texts.DONE_QUEUED
    await show(callback, bot, panel, await unit_screen(sysd, key))


@router.callback_query(Act.filter(F.a.in_({"start", "stop", "rst"})), Act.filter(F.p.in_(settings.UNITS)))
async def on_control(
    callback: CallbackQuery, callback_data: Act, callback_answer: CallbackAnswer,
    bot: Bot, panel: Panel, sysd: Systemd, runtime: Runtime,
) -> None:
    data, key = callback_data, callback_data.p
    if data.ok:
        await _perform(callback, callback_answer, bot, panel, sysd, runtime, data)
        return
    text: str
    if data.a == "rst":
        text = texts.CONFIRM_RESTART_LIVE
    elif data.a == "stop":
        if key == "live":
            text = texts.CONFIRM_STOP_LIVE
        else:
            text = texts.CONFIRM_STOP_TASK.format(title=_title(key))
            if key == "crs":
                text += texts.CONFIRM_STOP_COURSES_NOTE
    elif key == "live":
        running = await status.running_exclusive(sysd)
        text = (
            texts.CONFIRM_START_LIVE_CONFLICT.format(task=_title(running[0]))
            if running
            else texts.CONFIRM_START_LIVE
        )
    else:  # start the courses replay
        busy = await _busy_text(sysd)
        if busy:
            callback_answer.text = busy
            callback_answer.show_alert = True
            return
        text = texts.CONFIRM_START_COURSES
    await show(callback, bot, panel, _confirm(text, data))


def cancel_screen(running: list[str]) -> tuple[str, InlineKeyboardMarkup]:
    return texts.CANCEL_PICK, keyboards.cancel_pick(running)
