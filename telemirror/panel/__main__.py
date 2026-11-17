"""Telegram control panel for telemirror.

    python -m telemirror.panel

Optional: without PANEL_BOT_TOKEN it logs that and exits 0 — the mirror itself
never depends on it (separate process / systemd unit).
"""

import asyncio
import logging
import sys

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from telemirror.misc.log_setup import setup_stdout_logger
from telemirror.panel import settings
from telemirror.panel.app import bot_commands, build_dispatcher


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
    dp = build_dispatcher(settings.ADMIN_IDS)
    await bot.set_my_commands(bot_commands())
    logger.info("Control panel started, admins: %s", sorted(settings.ADMIN_IDS))
    # Own process: let aiogram handle SIGTERM/SIGINT (graceful stop of polling).
    await dp.start_polling(bot)
    return 0


def main() -> None:
    logger = setup_stdout_logger("telemirror", settings.LOG_LEVEL)
    setup_stdout_logger("aiogram", logging.WARNING)
    sys.exit(asyncio.run(_run(logger.getChild("panel"))))


if __name__ == "__main__":
    main()
