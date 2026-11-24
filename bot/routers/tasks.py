"""📊 Статус: every project's units (mirror, history replay, maintenance) and a
unit's card with its journal — only shown here: a button opens the screen
that runs it (the project's card, ⏪, the tool), its title on it."""

import time
from typing import Optional

from aiogram import Router
from aiogram.types import Message

from bot import settings, status, texts
from bot.callbacks import NavCB
from bot.keyboards.common import button, paged_rows, pages
from bot.registry import SCREENS
from bot.routers import _units
from bot.runtime import Runtime
from bot.screens import open_screen, show, view
from bot.systemd import Systemd
from bot.texts import esc, unit_label
from telemirror.projects import Project, list_projects

router = Router(name="tasks")

@view("tsk")
async def tasks_view(message: Message, edit: bool, nav: NavCB, *, sysd: Systemd, note: str = "", **_) -> None:
    if not sysd.available:
        await show(message, edit, "tsk", body=texts.SYSTEMD_UNAVAILABLE, note=note)
        return
    shown = []  # a replay / a task only while it runs or after a failure — the mirror always
    for p in list_projects():
        for kind, unit in enumerate(p.units):
            st = await status.unit_state(sysd, unit)
            if unit == p.live_unit or (st and (st.running or st.active == "failed")):
                shown.append((p, kind, unit, st))
    page = nav.pg % pages(len(shown), settings.PAGE_SIZE)
    lines, items = [], []
    for n, (p, kind, unit, st) in enumerate(shown):
        label = f"{unit_label(p, unit)} · {_units.state_text(p, unit, st)}"
        items.append(button(texts.cut(label, 60), NavCB(s="unit", p=p.key, i=kind, pg=page)))
        # the rows are on the buttons; the text adds only a running replay's progress
        if unit == p.past_unit and page * settings.PAGE_SIZE <= n < (page + 1) * settings.PAGE_SIZE \
                and (line := await _units.progress(sysd, unit, st)):
            lines.append(f"{esc(label)}\n{line}")
    body = "\n\n".join(lines) if shown else "Проектов нет — нечего показывать."
    more = "Зеркала проектов видны всегда; история и инструменты — пока работают или после сбоя."
    own = paged_rows(items, page, settings.PAGE_SIZE, lambda pg: NavCB(s="tsk", pg=pg))
    await show(message, edit, "tsk", body=body, more=more if shown else "", note=note, own=own, pg=page)


@view("unit")
async def unit_view(message: Message, edit: bool, nav: NavCB, *, project: Project, sysd: Systemd,
                    note: str = "", **deps) -> None:
    kind = nav.i
    if not 0 <= kind < len(project.units):
        await open_screen(NavCB(s="tsk"), message, edit, {"sysd": sysd, **deps}, note=texts.STALE_BUTTON)
        return
    unit = project.units[kind]
    st = await status.unit_state(sysd, unit)
    lines = [f"<b>{esc(unit_label(project, unit))}</b>",
             f"Состояние: <b>{_units.state_text(project, unit, st)}</b>"]
    if st is not None:
        if st.since:
            lines.append(f"С {texts.fmt_ts(st.since)} ({texts.fmt_duration(time.time() - st.since)})")
        if unit == project.live_unit and st.restarts:
            lines.append(f"Автоматических перезапусков после сбоев: {st.restarts}")
        if st.running and st.memory:
            lines.append(f"Память: {texts.fmt_bytes(st.memory)}")
        if st.active == "failed" or (not st.running and st.result not in ("", "success")):
            lines.append(f"Последний запуск: <b>{texts.result_text(st.result)}</b>")
        if unit == project.past_unit and (line := await _units.progress(sysd, unit, st)):
            lines.append(line)
    journal = await _units.journal_text(sysd, unit, st)
    if not sysd.available:
        lines.append(texts.SYSTEMD_UNAVAILABLE)
    body = "\n".join(lines) + ("\n\n" + journal if journal else "")
    where = manage_nav(project, unit, deps.get("runtime"))
    to = SCREENS[where.s].title
    own = [[button(f"{to} ›", where)]]
    await show(message, edit, "unit", project, body=body, note=note, own=own,
               own_hints=[(to, "там это запускается и останавливается")], i=kind, pg=nav.pg)


def manage_nav(project: Project, unit: str, runtime: Optional[Runtime]) -> NavCB:
    """Where a unit is run from: the project's card, ⏪, or the tool that ran last."""
    if unit == project.live_unit:
        return NavCB(s="card", p=project.key)
    if unit == project.past_unit:
        return NavCB(s="rpl", p=project.key)
    last = max(((launch.at, task) for (key, task), launch in (runtime.launches.items() if runtime else ())
                if key == project.key), default=None)
    return NavCB(s=last[1] if last else "mnt", p=project.key)
