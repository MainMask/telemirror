"""Push notifications to the admins: the panel polls systemd and reports state
*transitions* of every project's units — a history replay / maintenance task
finished (ok / failed), a live mirror crashed, went failed, came back — and
brings back the mirrors paused for a shared session (``turns.due``). The first
poll only records the baseline, so a panel restart doesn't replay old events."""

import asyncio
import logging
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Callable, Optional

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from telemirror.panel import settings, status, turns
from telemirror.panel.callbacks import NavCB
from telemirror.panel.keyboards.common import back_kb
from telemirror.panel.screens import esc
from telemirror.panel.systemd import Systemd, UnitState
from telemirror.projects import Project, list_projects

logger = logging.getLogger(__name__)

KINDS = ("пересылка", "догрузка", "обслуживание")  # live / past / task — NavCB(s="unit").i
OPEN = "📊 Открыть"


def unit_kind(project: Project, unit: str) -> int:
    return project.units.index(unit)


def unit_label(project: Project, unit: str) -> str:
    return f"{project.icon} {project.name} · {KINDS[unit_kind(project, unit)]}"


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
        if st.active == "failed" and prev.active != "failed":
            return f"🔴 {label}: сбой (failed). systemd больше не перезапускает его сам."
        if prev.active == "failed" and st.running:
            return f"🟢 {label}: снова работает."
        if st.restarts > prev.restarts:
            now, last = self._clock(), self._last_crash.get(unit)
            if last is None or now - last >= settings.NOTIFY_COOLDOWN_SEC:
                self._last_crash[unit] = now
                return f"⚠️ {label}: упало и перезапущено systemd ({st.restarts} раз за всё время)."
        return None

    @staticmethod
    def _task(label: str, prev: UnitState, st: UnitState) -> Optional[str]:
        # Finished = was running and stopped, or a whole new run started and
        # ended between two polls (a new invocation that's already over).
        new_run = bool(st.invocation) and st.invocation != prev.invocation
        if st.running or not (prev.running or new_run):
            return None
        if st.active == "failed" or st.result not in ("", "success"):
            return f"‼️ {label}: завершилась с ошибкой ({esc(st.result or st.active)})."
        return f"✅ {label}: завершилась успешно."


async def _notify(bot: Bot, admin_ids: frozenset, text: str, nav: Optional[NavCB] = None) -> None:
    kb = back_kb(nav, OPEN) if nav else None
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
            by_unit = {u: p for p in found for u in p.units}
            for finished, resumed in await turns.due(sysd):
                names = ", ".join(esc(unit_label(by_unit[u], u)) for u in resumed if u in by_unit)
                if names:
                    after = esc(unit_label(by_unit[finished], finished)) if finished in by_unit else finished
                    await _notify(bot, admin_ids, f"▶️ Снова запущено: {names} — после «{after}».")
        except Exception as e:  # noqa: BLE001 - the loop must outlive one bad round
            logger.warning("panel: watcher round failed: %s: %s", type(e).__name__, e)
        await asyncio.sleep(settings.WATCH_INTERVAL_SEC)
