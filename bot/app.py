"""Dispatcher assembly — kept apart from ``__main__`` so tests can build it."""

import asyncio
import logging
from contextlib import suppress
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommand, ErrorEvent

from bot import pending, registry, texts
from bot.configstore import ConfigStore
from bot.middlewares import AdminOnly, AlbumMiddleware, ChatPicked, LeaveFormOnNavigation, Services
from bot.routers import (
    accounts,
    config_file,
    directions,
    failed,
    filters,
    maintenance,
    menu,
    params,
    projects,
    replay,
    settings,
    stale,
    tasks,
)
from bot.routers._common import HANDLED
from bot.runtime import Runtime
from bot.states import PanelStorage
from bot.systemd import Systemd
from bot.texts import esc
from bot.watcher import watch
from telemirror.misc.telegram_client import cancel_and_await

logger = logging.getLogger(__name__)

# menu first: a main-menu button or a command always wins over a form's step;
# stale last: a button / a message nobody took is still answered.
ROUTERS = (menu, projects, directions, filters, params, replay, maintenance, failed, config_file, tasks,
           accounts, settings, stale)

COMMANDS = {
    "start": "Главный экран",
    "status": "Что сейчас выполняется",
    "cancel": "Выйти из ввода",
}


def build_dispatcher(
    admin_ids: frozenset,
    sysd: Optional[Systemd] = None,
    store: Optional[ConfigStore] = None,
) -> Dispatcher:
    if missing := registry.unhandled_actions(HANDLED):
        raise RuntimeError(f"registry buttons without a handler: {missing}")
    if extra := registry.unknown_actions(HANDLED):
        raise RuntimeError(f"handlers of buttons the registry doesn't have: {extra}")
    # FSM state = short forms; losing it on a panel restart is harmless.
    dp = Dispatcher(storage=PanelStorage())
    dp.update.outer_middleware(AdminOnly(admin_ids))
    dp.update.outer_middleware(Services())
    dp.callback_query.outer_middleware(LeaveFormOnNavigation())
    dp.message.outer_middleware(ChatPicked())  # a chat picked at the bottom: the main menu back
    dp.message.middleware(AlbumMiddleware())  # a .session with its .json, sent together
    dp.errors.register(_on_error)
    dp.include_routers(*(module.router for module in ROUTERS))
    # Injected into handlers by parameter name.
    dp["sysd"] = sysd or Systemd()
    dp["store"] = store or ConfigStore()
    dp["runtime"] = Runtime()
    dp["admin_ids"] = admin_ids
    # Startup/shutdown fire only under start_polling (not in feed_update tests).
    dp.startup.register(_start_watcher)
    dp.shutdown.register(_stop_watcher)
    return dp


async def _start_watcher(bot: Bot, dispatcher: Dispatcher, sysd: Systemd, admin_ids: frozenset) -> None:
    if sysd.available:
        dispatcher["watch_task"] = asyncio.create_task(watch(bot, sysd, admin_ids))


async def _stop_watcher(dispatcher: Dispatcher) -> None:
    task = dispatcher.workflow_data.pop("watch_task", None)
    if task is not None:
        await cancel_and_await(task)
    await pending.close_all()  # a sign-in in progress: its client disconnects


async def _on_error(event: ErrorEvent, bot: Bot) -> None:
    """A handler crashed: log it with the traceback and tell the admin, instead
    of a silently dead button."""
    logger.error("panel: handler failed: %s", event.exception, exc_info=event.exception)
    update = event.update
    user = (
        update.callback_query.from_user if update.callback_query
        else update.message.from_user if update.message and update.message.from_user
        else None
    )
    if user is not None:
        with suppress(TelegramAPIError):
            await bot.send_message(user.id, texts.INTERNAL_ERROR.format(error=esc(type(event.exception).__name__)))


def bot_commands() -> list:
    return [BotCommand(command=c, description=d) for c, d in COMMANDS.items()]
