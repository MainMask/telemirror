"""What a form keeps between its steps outside the FSM, one item per chat: a
sign-in by phone waiting for its code (a live Telethon client can't go into
FSM data) or the files of a session upload waiting for its passcode (too big
for it) — or 📺 Канал · 👥 Группа shown at the bottom (``Picker``). An item is
dropped — a client disconnected, the main menu put back alone at the bottom —
when the chat leaves the form, after ``settings.PENDING_TTL_SEC`` of no answer
(a picker stays: the form still takes a pick), or when the panel stops, so an
abandoned form holds nothing for long."""

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Optional, TypeVar

from bot import settings, texts
from bot.keyboards.menu import main_menu

logger = logging.getLogger(__name__)


@dataclass
class Login:
    client: Any  # telethon.TelegramClient, connected
    phone: str
    phone_code_hash: str = ""


@dataclass
class Upload:
    files: dict  # name → bytes


@dataclass
class Picker:
    bot: Any  # aiogram.Bot: the main menu is put back by a message of its own


Item = TypeVar("Item", Login, Upload, Picker)

_items: dict = {}  # chat id → (item, its expiry task)


async def put(chat_id: int, item: Any) -> None:
    await close(chat_id, quiet=isinstance(item, Picker))  # a picker again: shown again, nothing to put back
    _items[chat_id] = (item, None if isinstance(item, Picker) else asyncio.create_task(_expire(chat_id)))


def get(chat_id: int, kind: type[Item]) -> Optional[Item]:
    item = _items.get(chat_id, (None, None))[0]
    return item if isinstance(item, kind) else None


async def close(chat_id: int, quiet: bool = False) -> None:
    """Drop the chat's item (left, done, failed or expired); ``quiet``: a picker
    without a message (a pick already put the menu back, or the panel stops)."""
    item, timer = _items.pop(chat_id, (None, None))
    if timer is not None and timer is not asyncio.current_task():
        timer.cancel()
    if isinstance(item, Login):
        with suppress(Exception):
            await item.client.disconnect()
    if isinstance(item, Picker) and not quiet:
        with suppress(Exception):  # best effort: the menu is back at the next pick or /start anyway
            await item.bot.send_message(chat_id, texts.PICK_CLOSED, reply_markup=main_menu())


async def close_all() -> None:
    """The panel stops: nothing stays connected."""
    for chat_id in list(_items):
        await close(chat_id, quiet=True)


async def _expire(chat_id: int) -> None:
    await asyncio.sleep(settings.PENDING_TTL_SEC)
    logger.info("panel: chat %s left its form unanswered — its pending %s dropped",
                chat_id, type(_items.get(chat_id, (None,))[0]).__name__)
    await close(chat_id)
