"""Telegram control panel for telemirror (a package of its own next to
``telemirror``, as in teleharvester).

    python -m bot

Optional: without PANEL_BOT_TOKEN it logs that and exits 0 — the mirror itself
never depends on it (separate process / systemd unit).
"""

import asyncio
import logging
import sys

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot import settings
from bot.app import bot_commands, build_dispatcher
from bot.safe_edit import SafeEdit
from telemirror.misc.log_setup import setup_stdout_logger


async def _run(logger: logging.Logger) -> int:
    if not settings.BOT_TOKEN:
        logger.info("PANEL_BOT_TOKEN is not set — the control panel is disabled")
        return 0
    if not settings.ADMIN_IDS:
        logger.error("PANEL_ADMIN_IDS is empty — refusing to start a panel nobody may use")
        return 1
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )
    # "message is not modified" / a message that can't be edited: handled once, here.
    bot.session.middleware(SafeEdit())
    dp = build_dispatcher(settings.ADMIN_IDS)
    await bot.set_my_commands(bot_commands())
    logger.info("Control panel started, admins: %s", sorted(settings.ADMIN_IDS))
    # Own process: let aiogram handle SIGTERM/SIGINT (graceful stop of polling).
    await dp.start_polling(bot)
    return 0


def main() -> None:
    logger = setup_stdout_logger("bot", settings.LOG_LEVEL)  # the panel's modules: bot.*
    setup_stdout_logger("telemirror", settings.LOG_LEVEL)  # what it uses of the mirror (projects, sessions)
    setup_stdout_logger("aiogram", logging.WARNING)
    sys.exit(asyncio.run(_run(logger)))


if __name__ == "__main__":
    main()
