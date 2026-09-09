"""Shared helpers for the ``skylon_set/*`` maintenance scripts.

Each script previously reimplemented the same client construction, retry loop,
entity classification and logging setup; this module is the single source.
"""

import asyncio
import contextlib
import logging
import sys
from contextlib import asynccontextmanager
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

from telethon import TelegramClient, utils
from telethon.errors import ChannelPrivateError, FloodWaitError
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetForumTopicsRequest


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


@asynccontextmanager
async def open_client(
    logger: logging.Logger, *, warn_main_running: bool = True, **client_kwargs
):
    """Connect a client from the shared session, verify auth, guarantee teardown.

    Yields ``(client, me)``. Replaces the connect + ``get_me`` check + "logged in
    as" line + ``try/finally`` disconnect that each script open-coded.
    """
    if warn_main_running:
        logger.warning(
            "Скрипт использует тот же SESSION_STRING, что и main.py. "
            "Убедитесь, что main.py НЕ запущен."
        )
    client = make_client(**client_kwargs)
    client.parse_mode = "markdown"
    await client.connect()
    try:
        me = await client.get_me()
        if me is None:
            raise RuntimeError(
                "Нет авторизации. Запустите login.py для получения SESSION_STRING."
            )
        at_username = f" (@{me.username})" if getattr(me, "username", None) else ""
        logger.info(f"Вошли как {utils.get_display_name(me)}{at_username}")
        yield client, me
    finally:
        await client.disconnect()


async def fetch_all_topics(client, peer) -> list:
    """Every forum topic of ``peer``, paginating past the 100-per-page API cap.

    ``ForumTopicDeleted`` tombstones (which carry only an ``id``) are dropped, so
    callers can rely on ``.title`` / ``.icon_*`` being present.
    """
    out, off_d, off_id, off_t = [], 0, 0, 0
    while True:
        r = await client(
            GetForumTopicsRequest(
                peer=peer,
                offset_date=off_d,
                offset_id=off_id,
                offset_topic=off_t,
                limit=100,
            )
        )
        out.extend(t for t in r.topics if getattr(t, "title", None) is not None)
        if len(r.topics) < 100:
            return out
        last = r.topics[-1]
        off_t = last.id
        off_id = getattr(last, "top_message", 0) or 0
        off_d = getattr(last, "date", 0) or 0
        await asyncio.sleep(0.3)


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
            with contextlib.suppress(Exception):
                await client.disconnect()
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
            with contextlib.suppress(Exception):
                await client.disconnect()
            await asyncio.sleep(10)
