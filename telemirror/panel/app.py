"""Dispatcher assembly — kept apart from ``__main__`` so tests can build it."""

from typing import Optional

from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from aiogram.utils.callback_answer import CallbackAnswerMiddleware

from telemirror.panel import texts
from telemirror.panel.configstore import ConfigStore
from telemirror.panel.middlewares import AdminOnly
from telemirror.panel.routers import maintenance, projects, settings, start, tasks
from telemirror.panel.runtime import Runtime
from telemirror.panel.systemd import Systemd
from telemirror.panel.ui import Panel


def build_dispatcher(
    admin_ids: frozenset[int],
    sysd: Optional[Systemd] = None,
    store: Optional[ConfigStore] = None,
) -> Dispatcher:
    # FSM state = short input dialogs; losing it on a panel restart is harmless.
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.outer_middleware(AdminOnly(admin_ids))
    # Answers every callback query (the handler can set text/show_alert).
    dp.callback_query.middleware(CallbackAnswerMiddleware())
    # start first: reply buttons and commands win over an active input state.
    dp.include_routers(start.router, tasks.router, projects.router, settings.router, maintenance.router)
    # Injected into handlers by parameter name.
    dp["sysd"] = sysd or Systemd()
    dp["store"] = store or ConfigStore()
    dp["panel"] = Panel()
    dp["runtime"] = Runtime()
    return dp


def bot_commands() -> list[BotCommand]:
    return [BotCommand(command=c, description=d) for c, d in texts.COMMANDS.items()]
