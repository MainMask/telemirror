"""Shared helpers for the ``telemirror.tasks`` maintenance scripts: the retry
loop, forum topics, entity classification (the account connection is
``telemirror.account.open_account``)."""

import asyncio
import contextlib

from telethon.errors import ChannelPrivateError, FloodWaitError
from telethon.tl.functions.messages import GetForumTopicsRequest


async def fetch_all_topics(client, peer) -> list:
    """Every forum topic of ``peer``, paginating past the 100-per-page API cap.

    ``ForumTopicDeleted`` tombstones (which carry only an ``id``) are dropped, so
    callers can rely on ``.title`` / ``.icon_*`` being present. A page with no
    topic not seen before ends it: whatever the API does with a cursor taken
    from a tombstone (no ``top_message``/``date``), it can't loop forever.
    """
    out: list = []
    seen: set = set()
    off_d, off_id, off_t = 0, 0, 0
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
        fresh = [t for t in r.topics if t.id not in seen]
        if r.topics and not fresh:
            return out  # the cursor went round
        seen.update(t.id for t in fresh)
        real = [t for t in r.topics if getattr(t, "title", None) is not None]
        out.extend(t for t in fresh if getattr(t, "title", None) is not None)
        if len(r.topics) < 100:
            return out
        # cursor is based on the last NON-deleted topic of the page: ForumTopicDeleted
        # has no top_message/date, and a zero cursor would break pagination
        last = real[-1] if real else r.topics[-1]
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
                print("Reconnecting...")
                await client.connect()
            result = await fn()
            await asyncio.sleep(0.5)
            return result
        except FloodWaitError as e:
            # the connection is fine: only transport errors below reconnect
            print(f"FloodWait: waiting {e.seconds}s...")
            await asyncio.sleep(e.seconds)
        except skip as e:
            print(f"  No access, skipping: {e}")
            return None
        except (ConnectionError, OSError) as e:
            transport_attempts += 1
            if transport_attempts > max_retries:
                print(f"Connection lost ({e}), {max_retries} attempts exhausted — aborting.")
                raise
            print(f"Connection lost ({e}), waiting 10s... ({transport_attempts}/{max_retries})")
            with contextlib.suppress(Exception):
                await client.disconnect()
            await asyncio.sleep(10)
