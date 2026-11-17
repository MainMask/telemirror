"""Screens are shown in place of the message their button is under (an edit).
Telegram refuses an edit in two harmless cases, handled here once for the whole
bot (a request middleware, registered in ``__main__``): the same text and
buttons again (a second tap) — nothing to do; a message it no longer lets be
edited (gone, too old, a document) — the text comes as a new message, so the
screen is never lost."""

from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import EditMessageReplyMarkup, EditMessageText, SendMessage

NOT_MODIFIED = "message is not modified"
NOT_EDITABLE = (
    "message can't be edited",
    "message to edit not found",
    "there is no text in the message to edit",
)


class SafeEdit(BaseRequestMiddleware):
    async def __call__(self, make_request, bot, method):
        if not isinstance(method, (EditMessageText, EditMessageReplyMarkup)):
            return await make_request(bot, method)
        try:
            return await make_request(bot, method)
        except TelegramBadRequest as err:
            why = err.message.lower()
            if NOT_MODIFIED in why:
                return True
            if not any(reason in why for reason in NOT_EDITABLE):
                raise
            if isinstance(method, EditMessageReplyMarkup):  # an old message's buttons: left as they are
                return True
            return await make_request(bot, SendMessage(
                chat_id=method.chat_id, text=method.text, parse_mode=method.parse_mode,
                entities=method.entities, reply_markup=method.reply_markup,
            ))
