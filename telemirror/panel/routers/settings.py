"""⚙️ Настройки: where the config comes from, access, monitoring."""

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

from telemirror.panel import configstore, keyboards, settings, texts
from telemirror.panel.callbacks import Nav
from telemirror.panel.systemd import Systemd, SystemdError
from telemirror.panel.ui import Panel, Screen, show

router = Router(name="settings")


async def _timer(sysd: Systemd, unit: str) -> str:
    try:
        st = await sysd.show(unit)
    except SystemdError:
        st = None
    if st is None:
        return texts.NO_DATA
    return texts.TIMER_ON if st.active == "active" else texts.TIMER_OFF


async def settings_screen(sysd: Systemd) -> Screen:
    reason = configstore.read_only_reason(settings.PROJECTS[0])
    source = {
        None: texts.SOURCE_FILE,
        "yaml_env": texts.SOURCE_YAML_ENV,
        "env_mode": texts.SOURCE_ENV,
    }.get(reason, texts.SOURCE_ENV)
    text = texts.SETTINGS_TITLE.format(
        source=source,
        admins=", ".join(f"<code>{i}</code>" for i in sorted(settings.ADMIN_IDS)),
        tech=texts.TECH_SET if settings.TECH_CHANNEL_SET else texts.TECH_UNSET,
        health=await _timer(sysd, settings.HEALTH_TIMER),
        restart=await _timer(sysd, settings.RESTART_TIMER),
    )
    if not sysd.available:
        text += "\n\n" + texts.SYSTEMD_UNAVAILABLE
    return text, keyboards.settings_screen()


@router.callback_query(Nav.filter(F.s == "set"))
async def on_settings(callback: CallbackQuery, bot: Bot, panel: Panel, sysd: Systemd) -> None:
    await show(callback, bot, panel, await settings_screen(sysd))
