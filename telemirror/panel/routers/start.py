"""/start, /status, /cancel and the persistent reply-keyboard navigation."""

from contextlib import suppress

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from telemirror.panel import keyboards, status, texts
from telemirror.panel.routers.projects import projects_screen
from telemirror.panel.routers.settings import settings_screen
from telemirror.panel.routers.tasks import cancel_screen, tasks_screen
from telemirror.panel.systemd import Systemd
from telemirror.panel.ui import Panel

router = Router(name="start")


async def home_text(first_name: str, sysd: Systemd) -> str:
    infos = [status.project_info(p) for p in status.visible_projects()]
    live = await status.unit_state(sysd, "live")
    return texts.home(
        first_name, len(infos), status.total_directions(infos), live.active if live else None
    )


@router.message(CommandStart())
async def on_start(message: Message, bot: Bot, panel: Panel, sysd: Systemd, state: FSMContext) -> None:
    await state.clear()
    name = message.from_user.first_name if message.from_user else ""
    await panel.delete_old(bot, message.chat.id)
    await message.answer(await home_text(name, sysd), reply_markup=keyboards.main_reply())


async def _open(message: Message, bot: Bot, panel: Panel, state: FSMContext, screen: tuple) -> None:
    """Reply-keyboard / command navigation: leaves any input mode, drops the
    tapped button's own message and replaces the panel message."""
    await state.clear()
    with suppress(TelegramBadRequest):
        await message.delete()
    await panel.send(bot, message.chat.id, screen[0], screen[1])


@router.message(F.text == texts.BTN_PROJECTS)
async def on_projects(message: Message, bot: Bot, panel: Panel, sysd: Systemd, state: FSMContext) -> None:
    await _open(message, bot, panel, state, await projects_screen(sysd))


@router.message(F.text == texts.BTN_TASKS)
@router.message(Command("status"))
async def on_tasks(message: Message, bot: Bot, panel: Panel, sysd: Systemd, state: FSMContext) -> None:
    await _open(message, bot, panel, state, await tasks_screen(sysd))


@router.message(F.text == texts.BTN_SETTINGS)
async def on_settings(message: Message, bot: Bot, panel: Panel, sysd: Systemd, state: FSMContext) -> None:
    await _open(message, bot, panel, state, await settings_screen(sysd))


@router.message(Command("cancel"))
async def on_cancel(message: Message, bot: Bot, panel: Panel, sysd: Systemd, state: FSMContext) -> None:
    if await state.get_state() is not None:
        await _open(message, bot, panel, state, (texts.CANCEL_INPUT, None))
        return
    running = await status.running_exclusive(sysd)
    screen = cancel_screen(running) if running else (texts.CANCEL_NOTHING, None)
    await _open(message, bot, panel, state, screen)
