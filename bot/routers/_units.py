"""Starting and stopping a project's units — its mirror, its history replay,
its maintenance task — the same way from every screen (📁 Проект, 📊 Задача,
⏪ История, 🛠 Инструменты): systemd and the session checked, the restart
cooldown kept, a question first when the start stops something else on the
session (``turns``), then the screen it came from reopened with the outcome."""

import logging
from typing import Optional

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot import settings, status, texts, turns
from bot.callbacks import NavCB
from bot.registry import YES
from bot.routers._common import (
    ask_confirm,
    confirmed,
    message_of,
    session_ok,
    stale_tap,
    systemd_ready,
)
from bot.runtime import Runtime
from bot.screens import open_screen
from bot.systemd import Systemd, SystemdError, UnitState
from bot.texts import esc, head, unit_label
from telemirror.projects import Project

logger = logging.getLogger(__name__)

STARTING, STOPPING, RESTARTING = "▶️ Запускается.", "⏹ Останавливается.", "🔁 Перезапускается."

_PROGRESS_GREP = r"\[Progress\]|\[PastMode\]"


def mask(text: str) -> str:
    return text.replace(settings.BOT_TOKEN, "***") if settings.BOT_TOKEN else text


def state_text(project: Project, unit: str, st: Optional[UnitState]) -> str:
    active = st.active if st else None
    state = texts.mirror_state(active) if unit == project.live_unit else texts.task_state(active)
    return f"{texts.state_icon(active)} {state}"


async def progress(sysd: Systemd, unit: str, st: Optional[UnitState]) -> str:
    """The last history-replay progress line of the current run, verbatim."""
    if st is None or not st.running or not st.invocation:
        return ""
    try:
        line = await sysd.journal(unit, 1, st.invocation, _PROGRESS_GREP)
    except SystemdError:
        return ""
    return f"<b>Сейчас:</b> <code>{esc(mask(line))}</code>" if line else ""


def pause_text(holders: list, mirror: bool = False) -> str:
    """What starting will stop, for a confirmation ("" — nothing): ``mirror``
    — a mirror replaces them (turned off), else they're paused for a run."""
    if not holders:
        return ""
    names = "\n".join(f"• {esc(unit_label(p, u))}" for p, u in holders)
    after = (
        "Это будет выключено: с одного аккаунта одновременно работает одно зеркало."
        if mirror else "Это будет приостановлено и запустится снова, когда закончится."
    )
    return f"\n\nС этого же аккаунта сейчас работает:\n{names}\n{after}"


async def can_start(callback: CallbackQuery, sysd: Systemd, runtime: Runtime, project: Project,
                    unit: str) -> bool:
    """systemd, the session file, the cooldown; False after saying why not."""
    if not await systemd_ready(callback, sysd) or not await session_ok(callback, project):
        return False
    if left := runtime.cooldown_left(unit):
        await stale_tap(callback, texts.COOLDOWN.format(sec=left))
        return False
    return True


async def ask_start(callback: CallbackQuery, state: FSMContext, sysd: Systemd, project: Project, unit: str,
                    question: str, back: NavCB, *, always: bool = False, kind: str = "unit_start",
                    yes: str = YES, **action) -> bool:
    """Ask first (a ``kind`` confirmation) when the start stops something on
    the session, or ``always``; True: nothing to ask — start now."""
    holders = await status.session_holders(sysd, project, besides=unit)
    if not holders and not always:
        return True
    await ask_confirm(callback, state, question + pause_text(holders, unit == project.live_unit), kind, back,
                      yes=yes, p=project.key, unit=unit, **action)
    return False


async def launch(callback: CallbackQuery, sysd: Systemd, runtime: Runtime, project: Project, unit: str,
                 *, restart: bool = False) -> bool:
    """``turns.start`` (the cooldown again: time passed since a question)."""
    if left := runtime.cooldown_left(unit):
        await stale_tap(callback, texts.COOLDOWN.format(sec=left))
        return False
    try:
        await turns.start(sysd, runtime, project, unit, restart=restart)
    except SystemdError as e:
        logger.error("panel: starting %s failed: %s", unit, e)
        await stale_tap(callback, texts.SYSTEMD_ERROR.format(detail=str(e)[:150]))
        return False
    await callback.answer(texts.COMMAND_SENT)
    return True


async def ask_stop(callback: CallbackQuery, state: FSMContext, sysd: Systemd, project: Project, unit: str,
                   restart: bool, back: NavCB) -> None:
    """⏹ / 🔁 of a unit: what it means, then «Да»."""
    if not await systemd_ready(callback, sysd):
        return
    if restart:
        what = ("Новые настройки начнут действовать; на несколько секунд копирование приостановится."
                + pause_text(await status.session_holders(sysd, project, besides=unit), mirror=True))
    elif unit == project.live_unit:
        what = ("Новые посты перестанут копироваться, пока вы не запустите снова. Ночной перезапуск "
                "по расписанию остановленное зеркало не включает.")
    elif unit == project.past_unit:
        what = ("В следующий раз копирование истории продолжится с того же места; зеркала, "
                "приостановленные ради него, запустятся снова.")
    else:
        what = "Зеркала, приостановленные ради этого, запустятся снова."
    verb = "🔁 Перезапустить" if restart else "⏹ Остановить"
    await ask_confirm(callback, state, f"{head(verb)} «{esc(unit_label(project, unit))}»?\n\n{what}",
                      "unit_restart" if restart else "unit_stop", back, p=project.key, unit=unit)


@confirmed("unit_start")
async def do_start(callback: CallbackQuery, action: dict, state: FSMContext, project: Project, deps: dict,
                   **_) -> None:
    if await launch(callback, deps["sysd"], deps["runtime"], project, action["unit"]):
        await open_screen(NavCB.unpack(action["back"]), message_of(callback), True, deps, note=STARTING)


@confirmed("unit_stop")
@confirmed("unit_restart")
async def do_stop(callback: CallbackQuery, action: dict, state: FSMContext, project: Project, deps: dict,
                  **_) -> None:
    unit, sysd = action["unit"], deps["sysd"]
    if unit not in project.units:
        await stale_tap(callback)
        return
    restart = action["kind"] == "unit_restart"
    if restart:
        if not await launch(callback, sysd, deps["runtime"], project, unit, restart=True):
            return
    else:
        try:
            # the mirror is turned off for good (not on the next boot either); a run just stops
            await (sysd.disable(unit) if unit == project.live_unit else sysd.stop(unit))
        except SystemdError as e:
            await stale_tap(callback, texts.SYSTEMD_ERROR.format(detail=str(e)[:150]))
            return
        await callback.answer(texts.COMMAND_SENT)
    await open_screen(NavCB.unpack(action["back"]), message_of(callback), True, deps,
                      note=RESTARTING if restart else STOPPING)


async def journal_text(sysd: Systemd, unit: str, st: Optional[UnitState]) -> str:
    """The unit's last run in the journal ("" — systemd knows nothing of it)."""
    if st is None:
        return ""
    try:
        raw = await sysd.journal(unit, settings.JOURNAL_LINES, st.invocation)
    except SystemdError as e:
        raw = str(e)
    raw = mask(raw)[-settings.JOURNAL_MAX_CHARS:]
    return (f"<b>Журнал последнего запуска</b> (последние {settings.JOURNAL_LINES} строк, технические "
            f"подробности):\n<pre>{esc(raw)}</pre>"
            if raw else "<i>Журнал пуст.</i>")
