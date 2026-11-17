"""⚙️ Настройки: access (read-only — it lives in .env), the monitoring timers
(on/off) and its 👤 Аккаунты (routers/accounts.py)."""

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from telemirror.panel import settings, texts
from telemirror.panel.callbacks import ActCB, NavCB
from telemirror.panel.registry import title
from telemirror.panel.routers._common import ask_confirm, confirmed, message_of, on_action, stale_tap
from telemirror.panel.screens import head, show, view
from telemirror.panel.systemd import Systemd, SystemdError

router = Router(name="settings")


async def _timer(sysd: Systemd, unit: str) -> str:
    try:
        st = await sysd.show(unit)
    except SystemdError:
        st = None
    if st is None:
        return texts.NO_DATA
    return "включена" if st.active == "active" else "выключена"


@view("set")
async def settings_view(message: Message, edit: bool, nav: NavCB, state: FSMContext, sysd: Systemd,
                        note: str = "", **_) -> None:
    lines = [
        "<b>Администраторы панели:</b> " + ", ".join(f"<code>{i}</code>" for i in sorted(settings.ADMIN_IDS)),
        "<b>Мониторинг:</b>",
        f"• проверка здоровья зеркал каждые 10 мин — {await _timer(sysd, settings.HEALTH_TIMER)}",
        f"• ежедневный перезапуск в 04:00 — {await _timer(sysd, settings.RESTART_TIMER)}",
        f"• уведомления в бот: проверка каждые {settings.WATCH_INTERVAL_SEC} с" if sysd.available
        else f"• уведомления в бот — {texts.NO_DATA}",
        "<i>Доступ и токен задаются в .env (PANEL_ADMIN_IDS, PANEL_BOT_TOKEN); панель их не меняет "
        "и секреты не показывает.</i>",
    ]
    titles: dict = {}
    hidden: tuple = ()
    if sysd.available:
        for action, unit in TIMER_OF.items():
            titles[action] = f"{title(action)}: {await _timer(sysd, unit)}"
    else:
        lines.append(texts.SYSTEMD_UNAVAILABLE)
        hidden = tuple(TIMER_OF)
    await show(message, edit, "set", body="\n".join(lines), note=note, titles=titles, hidden=hidden)


TIMER_OF = {"set_health": settings.HEALTH_TIMER, "set_restart": settings.RESTART_TIMER}
TIMER_OFF_NOTE = {
    "set_health": "Падающее по кругу зеркало перестанет поднимать тревогу (уведомления о падении "
                  "из бота останутся).",
    "set_restart": "Сохранённые в панели изменения конфигурации будут применяться только после "
                   "🔁 Перезапустить в карточке проекта.",
}


async def _active(sysd: Systemd, unit: str):
    try:
        st = await sysd.show(unit)
    except SystemdError:
        return None
    return None if st is None else st.active == "active"


@on_action(router, *TIMER_OF)
async def on_timer(callback: CallbackQuery, callback_data: ActCB, state: FSMContext, sysd: Systemd) -> None:
    if not sysd.available:
        await stale_tap(callback, texts.SYSTEMD_UNAVAILABLE)
        return
    on = await _active(sysd, TIMER_OF[callback_data.a])
    if on is None:
        await stale_tap(callback, texts.SYSTEMD_ERROR.format(detail=texts.NO_DATA))
        return
    what = (f"Выключить?\n\n{TIMER_OFF_NOTE[callback_data.a]}" if on
            else "Включить? Таймер будет запускаться и после перезагрузки сервера.")
    await ask_confirm(callback, state, f"{head(title(callback_data.a))}: {what}", "timer",
                      NavCB(s="set"), a=callback_data.a, on=not on)


@confirmed("timer")
async def do_timer(callback: CallbackQuery, action: dict, state: FSMContext, sysd: Systemd, **_) -> None:
    unit = TIMER_OF[action["a"]]
    try:
        await (sysd.enable(unit) if action["on"] else sysd.disable(unit))
    except SystemdError as e:
        await stale_tap(callback, texts.SYSTEMD_ERROR.format(detail=str(e)[:150]))
        return
    await callback.answer()
    await settings_view(message_of(callback), True, NavCB(s="set"), state, sysd,
                        note=f"{'▶️ Включено' if action['on'] else '⏹ Выключено'}: {title(action['a'])}.")
