import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from telemirror.panel.routers._common import leave_form

logger = logging.getLogger(__name__)


class AdminOnly(BaseMiddleware):
    """Outer middleware on ``Dispatcher.update``: drops every update whose
    sender isn't in ``admin_ids`` before any handler (or FSM) sees it."""

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
    to a field the admin abandoned (e.g. "-" silently clearing tech_channel)."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        state = data.get("state")
        payload = getattr(event, "data", None) or ""
        if state is not None and not payload.startswith("c:") and await state.get_state() is not None:
            await leave_form(data["event_from_user"].id, state)
        return await handler(event, data)


class AlbumMiddleware(BaseMiddleware):
    """Files sent together (an album: a .session with its .json) reach the
    handler once: Telegram sends each item as its own update. The first item
    waits until none has come for ``LATENCY`` seconds, then runs the handler
    with all of them as ``album``; the others are swallowed. A single message
    gets ``album=None`` (as teleharvester's bot/services/album.py)."""

    LATENCY = 0.7

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
        seen = 0
        while seen != len(bucket):  # another item came meanwhile: wait for the next one
            seen = len(bucket)
            await asyncio.sleep(self.LATENCY)
        album = sorted(self._albums.pop(group, [event]), key=lambda m: m.message_id)
        data["album"] = album
        return await handler(event, data)
