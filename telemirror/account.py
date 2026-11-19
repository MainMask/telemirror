"""The one way a script connects to the configured account (``telemirror.config``):
the session lock, the client with the session's fingerprint, a bounded
connect, the authorization check, a clean disconnect. Used by the history
replay (``telemirror.past``) and every maintenance task (``telemirror.tasks``).
"""

import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional, Tuple

from telethon import TelegramClient, utils

from telemirror import config
from telemirror.misc.session_lock import SessionBusy, lock_session
from telemirror.misc.telegram_client import build_telegram_client, connect_with_timeout

NOT_AUTHORIZED = (
    "Not authorized. Sign in again (python -m telemirror.login, or 👤 Аккаунты in the "
    "panel) and give the project the new session."
)


@asynccontextmanager
async def open_account(
    logger: logging.Logger,
    *,
    connection_retries: int = 5,
    retry_delay: int = 1,
    flood_sleep_threshold: Optional[int] = None,
) -> AsyncIterator[Tuple[TelegramClient, object]]:
    """Yields ``(client, me)``; exits the process with the holder's name when
    another process has the session (``telemirror.misc.session_lock``)."""
    if config.SESSION_FILE:
        try:
            lock_session(config.SESSION_FILE)
        except SessionBusy as e:
            sys.exit(str(e))
    client = build_telegram_client(
        config.SESSION_STRING,
        config.API_ID,
        config.API_HASH,
        device_model=config.API_DEVICE_MODEL,
        system_version=config.API_SYSTEM_VERSION,
        app_version=config.API_APP_VERSION,
        lang_pack=config.API_LANG_PACK,
        system_lang_code=config.API_SYSTEM_LANG_CODE,
        connection_retries=connection_retries,
        retry_delay=retry_delay,
    )
    if flood_sleep_threshold is not None:
        client.flood_sleep_threshold = flood_sleep_threshold
    try:
        await connect_with_timeout(client)
        me = await client.get_me()
        if me is None:
            raise RuntimeError(NOT_AUTHORIZED)
        at_username = f" (@{me.username})" if getattr(me, "username", None) else ""
        logger.info(f"Logged in as {utils.get_display_name(me)}{at_username}")
        yield client, me
    finally:
        await client.disconnect()
