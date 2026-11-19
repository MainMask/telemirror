"""⚙️ Настройки: access (read-only — it lives in .env), the monitoring timers
(on/off), 🧾 Проверка установки (telemirror.selfcheck) and its 👤 Аккаунты
(routers/accounts.py)."""

import asyncio
from typing import Optional

from aiogram import Router
from aiogram.types import CallbackQuery, Message

from bot import settings, status, texts
from bot.callbacks import ActCB, NavCB
from bot.registry import title
from bot.routers._common import (
    message_of,
    on_action,
    stale_tap,
    systemd_ready,
)
from bot.screens import open_screen, show, view
from bot.systemd import Systemd, SystemdError
from telemirror import selfcheck

router = Router(name="settings")

TIMER_OF = {"set_health": settings.HEALTH_TIMER, "set_restart": settings.RESTART_TIMER,
            "set_report": settings.REPORT_TIMER}
TIMER_OFF_NOTE = {
    "set_health": "Если зеркало будет падать снова и снова, отдельного предупреждения не будет "
                  "(обычные уведомления о сбоях останутся).",
    "set_restart": "Изменения, сохранённые в панели, будут начинать действовать только после "
                   f"«{title('restart')}» в карточке проекта.",
    "set_report": "Сводка по понедельникам приходить не будет (уведомления о сбоях останутся).",
}


async def _timer_on(sysd: Systemd, unit: str) -> Optional[bool]:
    st = await status.unit_state(sysd, unit)
    return None if st is None else st.active == "active"


def _on_text(on: Optional[bool]) -> str:
    return texts.NO_DATA if on is None else texts.on_off(on)


@view("set")
async def settings_view(message: Message, edit: bool, nav: NavCB, *, sysd: Systemd, note: str = "",
                        **_) -> None:
    lines = [
        f"🔔 Уведомления о сбоях приходят сюда, в бот: проверка каждые {settings.WATCH_INTERVAL_SEC} с"
        if sysd.available else f"🔔 Уведомления о сбоях сюда, в бот — {texts.NO_DATA}",
    ]
    more = ("Кто может пользоваться панелью (ID в Telegram): "
            + ", ".join(f"<code>{i}</code>" for i in sorted(settings.ADMIN_IDS))
            + ". Список меняется в настройках сервера (PANEL_ADMIN_IDS в .env), не здесь.")
    titles: dict = {}
    hidden: tuple = ()
    if sysd.available:
        for action, unit in TIMER_OF.items():
            titles[action] = f"{title(action)}: {_on_text(await _timer_on(sysd, unit))}"
    else:
        lines.append(texts.SYSTEMD_UNAVAILABLE)
        hidden = tuple(TIMER_OF)
    await show(message, edit, "set", body="\n".join(lines), more=more, note=note, titles=titles, hidden=hidden)


@on_action(router, *TIMER_OF)
async def on_timer(callback: CallbackQuery, callback_data: ActCB, sysd: Systemd, deps: dict) -> None:
    """A switch, as every other one: no question — turning it back is one tap."""
    if not await systemd_ready(callback, sysd):
        return
    unit = TIMER_OF[callback_data.a]
    on = await _timer_on(sysd, unit)
    if on is None:
        await stale_tap(callback, texts.SYSTEMD_ERROR.format(detail=texts.NO_DATA))
        return
    try:
        await (sysd.disable(unit) if on else sysd.enable(unit))
    except SystemdError as e:
        await stale_tap(callback, texts.SYSTEMD_ERROR.format(detail=str(e)[:150]))
        return
    await callback.answer()
    note = (f"⏹ Выключено: {title(callback_data.a)}. {TIMER_OFF_NOTE[callback_data.a]}" if on
            else f"▶️ Включено: {title(callback_data.a)}. Таймер будет запускаться и после перезагрузки сервера.")
    await open_screen(NavCB(s="set"), message_of(callback), True, deps, note=note)


@view("chk")
async def selfcheck_view(message: Message, edit: bool, nav: NavCB, *, note: str = "", **_) -> None:
    """Only reads, takes a few seconds (each project's config is loaded in a
    subprocess): ⏳ meanwhile, in the message's place."""
    if edit:
        await message.edit_text(texts.SELFCHECK_WAIT)
    checks = await asyncio.to_thread(selfcheck.run)
    body = "\n".join([selfcheck.summary(checks), "", *(texts.esc(c.line()) for c in checks)])
    await show(message, edit, "chk", body=body, note=note, more=texts.SELFCHECK_MORE)
