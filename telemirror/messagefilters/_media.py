"""Shared media helpers for filters that re-upload a message's media."""

import asyncio
import contextvars
import logging
import os
import tempfile
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from typing import Any, Optional

from telethon.tl import types

from ..hints import EventMessage
from ..misc.links import private_message_link

logger = logging.getLogger(__name__)

# Telegram upload limit for accounts without a Premium subscription.
# Larger files can't be re-uploaded through this session.
UPLOAD_LIMIT_BYTES = 2 * 1024**3

# ~20 min of retries across 7 attempts. past_mode adds its own outer retry loop;
# the live mirror relies on this budget alone before it degrades to the original.
_DOWNLOAD_RETRY_DELAYS = (15, 45, 90, 180, 300, 600)  # seconds between attempts

# True while past_mode is replaying: a filter that still can't download re-raises
# MediaDownloadError so the checkpoint stays put and the message is retried.
# False (live mirror): the filter mirrors the original instead of dropping it.
# Set per message by EventProcessor; asyncio copies it into each update's task.
strict_media_mode: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "strict_media_mode", default=False
)


class MediaDownloadError(Exception):
    """Raised by ``download_media_with_retry`` once its spaced retries are spent
    on a *transient* Telegram file-serving failure.

    A filter re-raises it only under ``strict_media_mode`` (past_mode) so its
    retry wrapper re-runs from the checkpoint instead of committing a degraded
    mirror; the live mirror mirrors the original (un-watermarked / unrenamed)
    rather than lose the message. ``message_id`` is the source message that
    could not be downloaded — past_mode uses it to skip past a permanently
    stuck message instead of retrying forever.
    """

    def __init__(self, *args, message_id: Optional[int] = None) -> None:
        super().__init__(*args)
        self.message_id = message_id


async def download_media_with_retry(message: EventMessage, **kwargs):
    """``message._client.download_media(message=message, **kwargs)`` with spaced
    retries over transient Telegram file-serving errors.

    A Telegram DC hiccup makes ``GetFileRequest`` time out; Telethon's own ``_call``
    retries its server errors ~6× over ~12s and, with ``raise_last_call_error``
    off, collapses them into ``ValueError('Request was unsuccessful N time(s)')`` —
    so that string is the only ValueError worth a slow retry, a bare one is a real
    bug. FloodWaitError is a deliberate omission: it must reach past_mode's retry
    wrapper. When the retries are spent the failure is re-raised as
    ``MediaDownloadError``; a non-transient error propagates unchanged.
    """
    attempts = len(_DOWNLOAD_RETRY_DELAYS) + 1
    for i in range(attempts):
        try:
            return await message._client.download_media(message=message, **kwargs)
        except (ConnectionError, asyncio.TimeoutError, ValueError) as e:
            transient = not isinstance(e, ValueError) or "unsuccessful" in str(e)
            if not transient:
                raise
            link = private_message_link(message.chat_id, message.id)
            if i == attempts - 1:
                raise MediaDownloadError(
                    f"{link}: download failed after {attempts} attempts ({e})",
                    message_id=message.id,
                ) from e
            delay = _DOWNLOAD_RETRY_DELAYS[i]
            logger.warning(
                "media download failed (%s: %s) %s — retry %d/%d in %ds",
                type(e).__name__,
                e,
                link,
                i + 1,
                attempts - 1,
                delay,
            )
            await asyncio.sleep(delay)


class ReuploadCache:
    """TTL + LRU cache of re-uploaded media, keyed by the source media id.

    A filter that downloads+re-uploads media runs once per fan-out target
    (`mirroring.py` copies the message and re-runs the whole chain for each
    target). Caching the produced handle lets the same upload be re-sent to all
    targets instead of re-downloading N times. One instance is created per
    filter *instantiation* in `config.build_filters`, which in practice is
    process-wide whenever directions share the top-level `default_filters`
    (true for every currently deployed config) — only a direction with its
    own YAML `filters:` override gets an isolated instance. A shared instance
    means a burst of more than `size` distinct media items across unrelated
    source channels within the TTL window can evict each other's entries.
    Instances live for the process either way.
    """

    def __init__(self, size: int = 16, ttl: float = 600.0) -> None:
        self._size = size
        self._ttl = ttl
        self._data: OrderedDict[int, tuple[float, Any]] = OrderedDict()

    def get(self, key: int) -> Optional[Any]:
        entry = self._data.get(key)
        if entry is None:
            return None
        cached_at, value = entry
        if time.monotonic() - cached_at > self._ttl:
            del self._data[key]
            return None
        self._data.move_to_end(key)
        return value

    def put(self, key: int, value: Any) -> None:
        self._data[key] = (time.monotonic(), value)
        self._data.move_to_end(key)
        while len(self._data) > self._size:
            self._data.popitem(last=False)


def source_media_id(media: Optional["types.TypeMessageMedia"]) -> Optional[int]:
    """Stable id of the source photo/document, for `ReuploadCache` keys."""
    if isinstance(media, types.MessageMediaPhoto) and isinstance(
        media.photo, types.Photo
    ):
        return media.photo.id
    if isinstance(media, types.MessageMediaDocument) and isinstance(
        media.document, types.Document
    ):
        return media.document.id
    return None


def filename_of(document: types.Document) -> Optional[str]:
    """Return the ``DocumentAttributeFilename`` value, or ``None``."""
    return next(
        (
            a.file_name
            for a in document.attributes
            if isinstance(a, types.DocumentAttributeFilename)
        ),
        None,
    )


@asynccontextmanager
async def downloaded_tempfile(message: EventMessage, suffix: str = ""):
    """Download ``message``'s media to a temp file, yield its path, always clean up."""
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="telemirror-tmp-", suffix=suffix, delete=False
        ) as f:
            tmp_path = f.name
        await download_media_with_retry(message, file=tmp_path)
        yield tmp_path
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
