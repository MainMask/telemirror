"""Shared helpers for the ``skylon_set/*`` maintenance scripts.

Each script previously reimplemented the same client construction, retry loop,
entity classification and logging setup; this module is the single source.
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from config import (  # noqa: F401  (re-exported for scripts)
        API_APP_VERSION,
        API_DEVICE_MODEL,
        API_HASH,
        API_ID,
        API_SYSTEM_VERSION,
        SESSION_STRING,
    )
except Exception:
    print("Failed reading .env")
    raise

from telethon import TelegramClient
from telethon.errors import ChannelPrivateError, FloodWaitError
from telethon.sessions import StringSession

_LOG_FORMAT = "%(levelname)-5s %(asctime)s [%(filename)s:%(lineno)d]:%(name)s: %(message)s"


def make_client(**extra_kwargs) -> TelegramClient:
    """Build a TelegramClient from the shared session/env config."""
    return TelegramClient(
        StringSession(SESSION_STRING),
        API_ID,
        API_HASH,
        device_model=API_DEVICE_MODEL,
        system_version=API_SYSTEM_VERSION,
        app_version=API_APP_VERSION,
        **extra_kwargs,
    )


def configure_logging(
    name: str, level: str, *, attach_telethon: bool = False
) -> logging.Logger:
    """Attach a stdout handler with the project log format to ``name``."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))

    logger = logging.getLogger(name)
    logger.setLevel(level)
    if not logger.handlers:
        logger.addHandler(handler)

    if attach_telethon:
        telethon_logger = logging.getLogger("telethon")
        telethon_logger.setLevel(logging.WARNING)
        if not telethon_logger.handlers:
            telethon_logger.addHandler(handler)

    return logger


def entity_type(entity) -> str:
    if getattr(entity, "megagroup", False):
        return "supergroup"
    if getattr(entity, "broadcast", False):
        return "channel"
    return "other"


async def safe_call(client, fn, *, skip_errors: tuple = ()):
    """Call ``fn()`` with reconnect + FloodWait handling.

    ``ChannelPrivateError`` and any type in ``skip_errors`` are treated as
    "no access" and return ``None``. Retries reconnect/FloodWait forever.
    """
    skip = (ChannelPrivateError, *skip_errors)
    while True:
        try:
            if not client.is_connected():
                print("Переподключаюсь...")
                await client.connect()
            result = await fn()
            await asyncio.sleep(0.5)
            return result
        except FloodWaitError as e:
            print(f"FloodWait: ждём {e.seconds}с...")
            try:
                await client.disconnect()
            except Exception:
                pass
            await asyncio.sleep(e.seconds)
        except skip as e:
            print(f"  Нет доступа, пропускаю: {e}")
            return None
        except (ConnectionError, OSError) as e:
            print(f"Соединение потеряно ({e}), жду 10с...")
            try:
                await client.disconnect()
            except Exception:
                pass
            await asyncio.sleep(10)
