from typing import AsyncIterator, List, Union

from telethon.tl import types


async def iter_message_groups(
    messages,
) -> AsyncIterator[Union[types.Message, List[types.Message]]]:
    """Consume an async iterable of messages and yield either:

    - a standalone ``Message`` (no ``grouped_id``), or
    - a ``list[Message]`` for each maximal run of consecutive messages sharing
      one ``grouped_id`` (an album).

    Non-``Message`` items (service messages, ``None``) are skipped.
    """
    pending: List[types.Message] = []
    pending_gid = None

    async for msg in messages:
        if not isinstance(msg, types.Message):
            continue
        gid = getattr(msg, "grouped_id", None)
        if gid is not None and gid == pending_gid:
            pending.append(msg)
            continue
        if pending:
            yield pending
            pending = []
        if gid is not None:
            pending = [msg]
            pending_gid = gid
        else:
            pending_gid = None
            yield msg

    if pending:
        yield pending
