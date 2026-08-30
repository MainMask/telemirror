import logging
import mimetypes
import os
from typing import Type

from telethon import errors
from telethon.tl import types

from ..hints import EventLike, EventMessage
from ._media import (
    UPLOAD_LIMIT_BYTES,
    ReuploadCache,
    downloaded_tempfile,
    filename_of,
    source_media_id,
)
from .base import FilterAction, FilterResult, MessageFilter

logger = logging.getLogger(__name__)


class RestrictSavingContentBypassFilter(MessageFilter):
    """Bypasses Telegram's `restrict saving content` (noforwards) protection.

    Downloads media from a protected source message and re-uploads it as a
    fresh file, so the outgoing message no longer references the protected
    origin. Non-file media (polls, geo, contacts, webpages, ...) isn't
    subject to this restriction and is passed through unchanged.
    """

    def __init__(self) -> None:
        # Re-send one re-upload to all fan-out targets (keyed by source id).
        self._cache = ReuploadCache()

    @property
    def restricted_content_allowed(self) -> bool:
        return True

    async def _process_message(
        self, message: EventMessage, event_type: Type[EventLike]
    ) -> FilterResult[EventMessage]:
        if not (message.chat and message.chat.noforwards and message.media):
            return FilterResult(FilterAction.CONTINUE, message)

        key = source_media_id(message.media)
        if key is not None:
            cached = self._cache.get(key)
            if cached is not None:
                message.media = cached
                return FilterResult(FilterAction.CONTINUE, message)

        if isinstance(message.media, types.MessageMediaDocument):
            doc = message.media.document
            if not isinstance(doc, types.Document):
                return FilterResult(FilterAction.DISCARD, message)
            if doc.size > UPLOAD_LIMIT_BYTES:
                logger.info(
                    "RestrictSavingContentBypassFilter: skipping %.2f GB file (chat_id=%s) — "
                    "exceeds the ~2GB upload limit for accounts without Telegram Premium",
                    doc.size / 1024**3,
                    message.chat_id,
                )
                return FilterResult(FilterAction.DISCARD, message)

        try:
            if isinstance(message.media, types.MessageMediaPhoto):
                new_media = await self._process_photo(message)
            elif isinstance(message.media, types.MessageMediaDocument):
                new_media = await self._process_document(message)
            else:
                new_media = None
        except (errors.FloodWaitError, errors.FloodPremiumWaitError):
            # A >threshold flood must reach past_mode's retry wrapper instead of
            # being turned into a silent DISCARD (checkpoint would advance past
            # an un-mirrored message). Same contract as mirroring.py.
            raise
        except Exception:
            logger.exception(
                "RestrictSavingContentBypassFilter: bypass failed (chat_id=%s)",
                message.chat_id,
            )
            return FilterResult(FilterAction.DISCARD, message)

        if new_media is not None:
            message.media = new_media
            if key is not None:
                self._cache.put(key, new_media)

        return FilterResult(FilterAction.CONTINUE, message)

    async def _process_photo(self, message: EventMessage):
        photo_bytes: bytes = await message._client.download_media(
            message=message, file=bytes
        )
        return await message._client.upload_file(photo_bytes, file_name="photo.jpg")

    async def _process_document(self, message: EventMessage):
        doc = message.media.document
        filename = filename_of(doc)
        suffix = (
            os.path.splitext(filename)[1]
            if filename
            else (mimetypes.guess_extension(doc.mime_type) or "")
        )

        async with downloaded_tempfile(message, suffix=suffix) as tmp_path:
            handle = await message._client.upload_file(
                tmp_path, file_name=filename or os.path.basename(tmp_path)
            )
        return types.InputMediaUploadedDocument(
            file=handle, mime_type=doc.mime_type, attributes=doc.attributes
        )
