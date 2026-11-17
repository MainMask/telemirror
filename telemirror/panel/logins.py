"""Sign-ins by phone in progress, one per chat: the Telethon client waiting
for its code lives here between the form's steps (it can't go into FSM data)."""

import logging
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class Login:
    client: Any  # telethon.TelegramClient
    phone: str
    phone_code_hash: str = ""


_open: dict = {}


def put(chat_id: int, login: Login) -> None:
    _open[chat_id] = login


def get(chat_id: int) -> Optional[Login]:
    return _open.get(chat_id)


async def close(chat_id: int) -> None:
    """Drop the chat's sign-in (left, done or failed): its client disconnects."""
    login = _open.pop(chat_id, None)
    if login is not None:
        with suppress(Exception):
            await login.client.disconnect()
