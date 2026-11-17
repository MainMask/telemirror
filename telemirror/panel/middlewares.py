import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

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
