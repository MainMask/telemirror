import logging
import mimetypes
import os
from typing import Type

from telethon.tl import types

from ..hints import EventLike, EventMessage
from ._media import (
    UPLOAD_LIMIT_BYTES,
    ReuploadCache,
    cached_reupload,
    download_media_with_retry,
    downloaded_tempfile,
    filename_of,
    reupload_errors,
)
from .base import FilterAction, FilterResult, MessageFilter

logger = logging.getLogger(__name__)

# Distinct from `None` (= "no processing needed for this media kind, pass
# through unchanged") so `_process_message` can tell a real reupload failure
# apart from a legitimately unhandled media kind and DISCARD only the former.
_REUPLOAD_FAILED = object()


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

        new_media = await self._reupload(message)
        if new_media is _REUPLOAD_FAILED:
            # live: protected media is unusable without a successful reupload
            # — there is nothing to mirror, so drop it (already logged).
            return FilterResult(FilterAction.DISCARD, message)

        if new_media is not None:
            message.media = new_media

        return FilterResult(FilterAction.CONTINUE, message)

    @cached_reupload(cacheable=lambda v: v is not None and v is not _REUPLOAD_FAILED)
    @reupload_errors(
        fallback=_REUPLOAD_FAILED,
        media_error_fmt=(
            "RestrictSavingContentBypassFilter: download failed, cannot bypass "
            "protection (chat_id=%s) — discarding"
        ),
        exception_fmt="RestrictSavingContentBypassFilter: bypass failed (chat_id=%s)",
    )
    async def _reupload(self, message: EventMessage):
        if isinstance(message.media, types.MessageMediaPhoto):
            return await self._process_photo(message)
        if isinstance(message.media, types.MessageMediaDocument):
            return await self._process_document(message)
        return None

    async def _process_photo(self, message: EventMessage):
        photo_bytes: bytes = await download_media_with_retry(message, file=bytes)
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
