import asyncio
import logging
from contextlib import suppress
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot import pending, settings, texts
from bot.callbacks import ChoiceCB
from bot.keyboards.menu import main_menu
from bot.states import leave_form

SERVICES = ("sysd", "store", "runtime")  # the dispatcher's workflow data views take by name

logger = logging.getLogger(__name__)


class AdminOnly(BaseMiddleware):
    """Outer middleware on ``Dispatcher.update``: drops every update whose
    sender isn't in ``admin_ids`` before any handler sees it (aiogram's FSM
    middleware runs first — ``states.PanelStorage`` keeps it from storing
    anything for a stranger)."""

    def __init__(self, admin_ids: frozenset[int]) -> None:
        if not admin_ids:
            raise ValueError("AdminOnly: admin_ids must not be empty")
        self._admin_ids = admin_ids

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None or user.id not in self._admin_ids:
            logger.warning(
                "panel: ignored an update from a non-admin user id=%s",
                getattr(user, "id", None),
            )
            return None
        return await handler(event, data)


class LeaveFormOnNavigation(BaseMiddleware):
    """Outer middleware on ``callback_query`` (runs before handler filters):
    only a form's own buttons (``ChoiceCB``, prefix ``c:``) keep the chat in its
    form; any other tap leaves it — so a later typed message can't be applied
    to a field the admin abandoned (e.g. "-" silently clearing the broadcast channel)."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        state = data.get("state")
        payload = getattr(event, "data", None) or ""
        if state is not None and not payload.startswith(f"{ChoiceCB.__prefix__}:") \
                and await state.get_state() is not None:
            await leave_form(data["event_from_user"].id, state)
        return await handler(event, data)


class DropStalePrompt(BaseMiddleware):
    """Outer middleware on ``message`` and ``callback_query``: a form's prompt
    sent as its own message (FSM data ``prompt`` — ``_common.start_form`` /
    ``ask``) loses its buttons once it is answered — the form over, or the next
    step's prompt sent —, so its ✖️ Отмена isn't left behind dead; the screen
    the form began under (``screen``) loses them once the form is over — the
    outcome is a screen of its own, below. A prompt asked again (a refused
    value) keeps them; so does a message whose own button was tapped (its
    handler shows something else in its place)."""

    KEYS = ("prompt", "screen")

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        state = data.get("state")
        if state is None:
            return await handler(event, data)
        form = await state.get_data()
        before = [form.get(key) for key in self.KEYS]
        result = await handler(event, data)
        form = await state.get_data()
        tapped = event.message.message_id if isinstance(event, CallbackQuery) and event.message else None
        for key, old in zip(self.KEYS, before, strict=True):
            if old is None or form.get(key) == old or old == tapped:
                continue
            with suppress(TelegramBadRequest):  # gone or too old: nothing to tidy
                await data["bot"].edit_message_reply_markup(
                    chat_id=data["event_from_user"].id, message_id=old, reply_markup=None)
        return result


class ChatPicked(BaseMiddleware):
    """Outer middleware on ``message``: a chat picked at the bottom
    (``keyboards.menu.chat_picker``) puts the main menu back there first —
    then reaches the form's step like a forwarded post (``_common.remember_chat``);
    with no form under way it is only answered."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        picked = getattr(event, "chat_shared", None)
        if picked is None or not isinstance(event, Message):
            return await handler(event, data)
        state = data.get("state")
        if state is None or await state.get_state() is None:
            await event.answer(texts.PICK_LATE, reply_markup=main_menu())
            return None
        await event.answer(texts.PICKED.format(title=texts.esc(picked.title or picked.chat_id)),
                           reply_markup=main_menu())
        await pending.close(event.chat.id, quiet=True)  # the menu is back already
        return await handler(event, data)


class AlbumMiddleware(BaseMiddleware):
    """Files sent together (an album: a .session with its .json) reach the
    handler once: Telegram sends each item as its own update. The first item
    waits until none has come for ``LATENCY`` seconds, then runs the handler
    with all of them as ``album``; the others are swallowed. A single message
    gets ``album=None`` (as teleharvester's bot/services/album.py)."""

    def __init__(self) -> None:
        self._albums: Dict[str, list] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        group = getattr(event, "media_group_id", None)
        if group is None:
            data["album"] = None
            return await handler(event, data)
        bucket = self._albums.setdefault(group, [])
        bucket.append(event)
        if len(bucket) > 1:  # not the first: the first carries the whole album
            return None
        try:
            seen = 0
            while seen != len(bucket):  # another item came meanwhile: wait for the next one
                seen = len(bucket)
                await asyncio.sleep(settings.ALBUM_LATENCY_SEC)
        finally:  # also when cancelled: the bucket mustn't outlive its wait
            self._albums.pop(group, None)
        album = sorted(bucket, key=lambda m: m.message_id)
        data["album"] = album
        return await handler(event, data)


class Services(BaseMiddleware):
    """Outer middleware on ``Dispatcher.update``: ``deps`` — the services
    (``SERVICES``) as one dict, for code that opens a screen on a handler's
    behalf (``screens.open_screen``, ``writes.save``)."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        data["deps"] = {key: data[key] for key in SERVICES}
        return await handler(event, data)
