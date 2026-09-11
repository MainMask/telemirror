"""Shared media helpers for filters that re-upload a message's media."""

import os
import tempfile
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from typing import Any, Optional

from telethon.tl import types

from ..hints import EventMessage

# Telegram upload limit for accounts without a Premium subscription.
# Larger files can't be re-uploaded through this session.
UPLOAD_LIMIT_BYTES = 2 * 1024**3


class ReuploadCache:
    """TTL + LRU cache of re-uploaded media, keyed by the source media id.

    A filter that downloads+re-uploads media runs once per fan-out target
    (`mirroring.py` copies the message and re-runs the whole chain for each
    target). Caching the produced handle lets the same upload be re-sent to all
    targets instead of re-downloading N times. Instances are created once per
    direction in `config.build_filters` and live for the process.
    """

    def __init__(self, size: int = 16, ttl: float = 600.0) -> None:
        self._size = size
        self._ttl = ttl
        self._data: "OrderedDict[int, tuple[float, Any]]" = OrderedDict()

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


def source_media_id(media) -> Optional[int]:
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
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            tmp_path = f.name
        await message._client.download_media(message=message, file=tmp_path)
        yield tmp_path
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
