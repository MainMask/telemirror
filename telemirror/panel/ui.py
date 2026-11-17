"""The single "panel message" per chat: sections edit it in place, a reply
button / command replaces it with a fresh one (and deletes the old one)."""

import logging
from contextlib import suppress
from typing import Optional, Union

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, ReplyKeyboardMarkup

logger = logging.getLogger(__name__)

Markup = Union[InlineKeyboardMarkup, ReplyKeyboardMarkup, None]
Screen = tuple[str, Optional[InlineKeyboardMarkup]]

_MAX_TEXT = 4096


def _fit(text: str) -> str:
    # Screens are built to stay far below the limit (paginated lists, capped
    # journal); this is only a last-resort guard against a Telegram error.
    return text if len(text) <= _MAX_TEXT else text[: _MAX_TEXT - 1] + "…"


class Panel:
    def __init__(self) -> None:
        self._ids: dict[int, int] = {}  # chat id → panel message id

    def forget(self, chat_id: int) -> Optional[int]:
        return self._ids.pop(chat_id, None)

    async def delete_old(self, bot: Bot, chat_id: int) -> None:
        old = self.forget(chat_id)
        if old is not None:
            with suppress(TelegramBadRequest, TelegramForbiddenError):
                await bot.delete_message(chat_id, old)

    async def send(self, bot: Bot, chat_id: int, text: str, markup: Markup = None) -> None:
        """New panel message; the previous one is deleted (best effort)."""
        await self.delete_old(bot, chat_id)
        msg = await bot.send_message(chat_id, _fit(text), reply_markup=markup)
        if not isinstance(markup, ReplyKeyboardMarkup):
            self._ids[chat_id] = msg.message_id

    async def edit(
        self,
        bot: Bot,
        chat_id: int,
        text: str,
        markup: Optional[InlineKeyboardMarkup],
        message_id: Optional[int] = None,
    ) -> None:
        """Edit the panel message in place (the one a button was pressed on,
        else the tracked one); fall back to a new message if that fails."""
        mid = message_id or self._ids.get(chat_id)
        if mid is None:
            await self.send(bot, chat_id, text, markup)
            return
        try:
            await bot.edit_message_text(
                text=_fit(text), chat_id=chat_id, message_id=mid, reply_markup=markup
            )
            self._ids[chat_id] = mid
        except TelegramBadRequest as e:
            if "message is not modified" in e.message:
                self._ids[chat_id] = mid
                return
            logger.info("panel: edit failed (%s), sending a new message", e.message)
            await self.send(bot, chat_id, text, markup)


async def show(callback: CallbackQuery, bot: Bot, panel: Panel, screen: Screen) -> None:
    """Render ``screen`` in place of the message the button was pressed on.
    The panel bot only talks to admins in private chats: chat id == user id."""
    text, markup = screen
    message_id = callback.message.message_id if callback.message else None
    await panel.edit(bot, callback.from_user.id, text, markup, message_id=message_id)
