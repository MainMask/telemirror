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
    from config import (
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

from telemirror.misc.log_setup import setup_stdout_logger


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


def configure_logging(name: str, level: str) -> logging.Logger:
    """Attach a stdout handler with the project log format to ``name``."""
    return setup_stdout_logger(name, level)


def entity_type(entity) -> str:
    if getattr(entity, "megagroup", False):
        return "supergroup"
    if getattr(entity, "broadcast", False):
        return "channel"
    return "other"


async def safe_call(client, fn, *, skip_errors: tuple = (), max_retries: int = 20):
    """Call ``fn()`` with reconnect + FloodWait handling.

    ``ChannelPrivateError`` and any type in ``skip_errors`` are treated as
    "no access" and return ``None``. FloodWait is always waited out; transport
    errors (``ConnectionError``/``OSError``) are retried up to ``max_retries``
    times, then re-raised so a dead session doesn't hang the script forever.
    """
    skip = (ChannelPrivateError, *skip_errors)
    transport_attempts = 0
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
            transport_attempts += 1
            if transport_attempts > max_retries:
                print(f"Соединение потеряно ({e}), исчерпаны {max_retries} попыток — прерываю.")
                raise
            print(f"Соединение потеряно ({e}), жду 10с... ({transport_attempts}/{max_retries})")
            try:
                await client.disconnect()
            except Exception:
                pass
            await asyncio.sleep(10)
