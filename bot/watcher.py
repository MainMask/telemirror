"""Push notifications to the admins: the panel polls systemd and reports state
*transitions* of every project's units — a history replay / maintenance task
finished, a live mirror crashed and was restarted, or came back from failed —
and
brings back the mirrors paused for a shared session (``turns.due``). The first
poll only records the baseline, so a panel restart doesn't replay old events.
A unit entering ``failed`` isn't told here: ``OnFailure=`` (``telemirror.alert``)
tells it at once, with the journal, even when the panel is down — one notice."""

import asyncio
import logging
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Callable, Optional

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from bot import settings, status, texts, turns
from bot.callbacks import NavCB
from bot.keyboards.common import back_kb
from bot.registry import TITLES
from bot.systemd import Systemd, UnitState
from bot.texts import esc, unit_kind, unit_label
from telemirror.projects import list_projects

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Notice:
    text: str
    nav: NavCB


class Watcher:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._prev: dict = {}
        self._last_crash: dict = {}

    def step(self, states: dict) -> list:
        """``states``: (project, unit) → UnitState (None: the query failed)."""
        out = []
        for (project, unit), st in states.items():
            if st is None:
                continue  # systemctl failed this round — keep the old baseline
            prev = self._prev.get(unit)
            self._prev[unit] = st
            if prev is None:
                continue
            nav = NavCB(s="unit", p=project.key, i=unit_kind(project, unit))
            label = esc(unit_label(project, unit))
            text = self._live(unit, label, prev, st) if unit == project.live_unit else self._task(label, prev, st)
            if text:
                out.append(Notice(text, nav))
        return out

    def _live(self, unit: str, label: str, prev: UnitState, st: UnitState) -> Optional[str]:
        if prev.active == "failed" and st.running:
            return f"🟢 {label}: снова работает."
        if st.restarts > prev.restarts:
            now, last = self._clock(), self._last_crash.get(unit)
            if last is None or now - last >= settings.NOTIFY_COOLDOWN_SEC:
                self._last_crash[unit] = now
                return f"⚠️ {label}: упало и запущено снова автоматически ({st.restarts} раз за всё время)."
        return None

    def forget_gone(self, units: set) -> None:
        """Drop what's kept of units no project has any more (deleted ones)."""
        for gone in [u for u in self._prev if u not in units]:
            del self._prev[gone]
            self._last_crash.pop(gone, None)

    @staticmethod
    def _task(label: str, prev: UnitState, st: UnitState) -> Optional[str]:
        # Finished = was running and stopped, or a whole new run started and
        # ended between two polls (a new invocation that's already over).
        new_run = bool(st.invocation) and st.invocation != prev.invocation
        if st.running or not (prev.running or new_run) or st.active == "failed":
            return None  # failed: OnFailure= has told it
        if st.result not in ("", "success"):
            why = "" if st.result in ("", "exit-code") else f" ({texts.result_text(st.result)})"
            return f"‼️ {label}: закончилось с ошибкой{why}."
        if not st.completed:  # systemd counts a SIGTERM stop (⏹, Conflicts=) as success too
            return f"⏹ {label}: прервано, не закончив работу."
        return f"✅ {label}: закончилось успешно."


async def _notify(bot: Bot, admin_ids: frozenset, text: str, nav: Optional[NavCB] = None) -> None:
    kb = back_kb(nav, TITLES["notice"]) if nav else None
    for admin in sorted(admin_ids):
        # An admin who never pressed /start can't be messaged — skip.
        with suppress(TelegramAPIError):
            await bot.send_message(admin, text, reply_markup=kb)


async def watch(bot: Bot, sysd: Systemd, admin_ids: frozenset) -> None:
    """Background loop (started on dispatcher startup, cancelled on shutdown)."""
    watcher = Watcher()
    while True:
        try:
            found = list_projects()
            states = {
                (p, unit): await status.unit_state(sysd, unit) for p in found for unit in p.units
            }
            for notice in watcher.step(states):
                await _notify(bot, admin_ids, notice.text, notice.nav)
            watcher.forget_gone({unit for _, unit in states})
            by_unit = {u: p for p in found for u in p.units}
            for finished, resumed in await turns.due(sysd):
                names = ", ".join(esc(unit_label(by_unit[u], u)) for u in resumed if u in by_unit)
                if names:
                    after = esc(unit_label(by_unit[finished], finished)) if finished in by_unit else finished
                    await _notify(bot, admin_ids, f"▶️ Снова запущено: {names} — после «{after}».")
        except Exception as e:  # noqa: BLE001 - the loop must outlive one bad round
            logger.warning("panel: watcher round failed: %s: %s", type(e).__name__, e)
        await asyncio.sleep(settings.WATCH_INTERVAL_SEC)
