"""Shared test helpers.

The filter pipeline is async but the project has no pytest-asyncio dependency,
so coroutines are driven synchronously with ``run()``.
"""

import asyncio

from telethon.tl import types


def run(coro):
    """Execute a coroutine to completion and return its result."""
    return asyncio.new_event_loop().run_until_complete(coro)


def make_message(text="", entities=None, media=None, channel_id=1000):
    """Build a minimal ``types.Message`` usable as filter input.

    ``message.chat_id`` resolves from ``peer_id`` to ``-100{channel_id}``.
    """
    return types.Message(
        id=1,
        peer_id=types.PeerChannel(channel_id),
        message=text,
        entities=entities,
        media=media,
    )


def entity_text(message, entity):
    """Return the substring an entity covers (UTF-16 offset/length aware)."""
    buf = message.message.encode("utf-16-le")
    return buf[entity.offset * 2 : (entity.offset + entity.length) * 2].decode("utf-16-le")
