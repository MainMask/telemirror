import logging
import os
import re
from typing import Optional, Type

from telethon.tl import types

from ..hints import EventLike, EventMessage
from ..misc.links import private_message_link
from ._media import (
    UPLOAD_LIMIT_BYTES,
    ReuploadCache,
    cached_media_result,
    cached_reupload,
    downloaded_tempfile,
    filename_of,
    reupload_errors,
)
from .base import FilterAction, FilterResult, MessageFilter

logger = logging.getLogger(__name__)


class DocumentFilenameFilter(MessageFilter):
    """Rewrites the filename of mirrored documents.

    Appends ``suffix`` and removes unwanted substrings (case-insensitive).
    Only documents that carry a ``DocumentAttributeFilename`` are affected;
    voice notes, photos, stickers and GIFs have no filename and pass through.

    Place after `RestrictSavingContentBypassFilter`: for a `noforwards` source
    that filter already re-uploads the file, so this one only patches the
    filename attribute in place. For a plain reference document it downloads
    and re-uploads the file with the new name (once per file, cached across a
    broadcast fan-out).

    Args:
        suffix (str): text appended as ``{name} - {suffix}``.
        remove (list[str]): substrings stripped from the filename.
    """

    def __init__(
        self, suffix: str = "", remove: Optional[list[str]] = None
    ) -> None:
        self._suffix = suffix
        self._remove_regex = None
        if remove:
            alternation = "|".join(
                re.escape(s) for s in sorted(remove, key=len, reverse=True)
            )
            # the fragment itself plus any bracket wrapping and one adjacent
            # separator, so removing it doesn't leave "[] " or "__" behind
            self._remove_regex = re.compile(
                rf"[\[({{]?\s*(?:{alternation})\s*[\])}}]?[ _-]?",
                flags=re.IGNORECASE,
            )

        self._cache = ReuploadCache()

    def _rename(self, name: str) -> str:
        stem, ext = os.path.splitext(name)

        # Idempotency: strip a suffix marker left by a previous pass (e.g.
        # cache hit, or reprocessing after RestrictSavingContentBypassFilter)
        # *before* `remove`-list cleanup runs, then re-append it
        # unconditionally below — rather than gating the append on an
        # "already suffixed?" flag computed before cleanup, which a `remove`
        # entry overlapping the suffix text could invalidate (stripping the
        # suffix out from under a flag that still thinks it's there).
        if self._suffix:
            if stem == self._suffix:
                stem = ""
            elif stem.endswith(f" - {self._suffix}"):
                stem = stem[: -len(f" - {self._suffix}")]

        if self._remove_regex is not None:
            stem = self._remove_regex.sub("", stem).strip(" _-")

        if self._suffix:
            stem = f"{stem} - {self._suffix}" if stem else self._suffix

        return f"{stem}{ext}"

    async def _process_message(
        self, message: EventMessage, event_type: Type[EventLike]
    ) -> FilterResult[EventMessage]:
        media = message.media

        # Already re-uploaded upstream (e.g. RestrictSavingContentBypassFilter):
        # patch the filename attribute in place, no download.
        if isinstance(media, types.InputMediaUploadedDocument):
            for attr in media.attributes:
                if isinstance(attr, types.DocumentAttributeFilename):
                    attr.file_name = self._rename(attr.file_name)
            return FilterResult(FilterAction.CONTINUE, message)

        if not isinstance(media, types.MessageMediaDocument) or not isinstance(
            media.document, types.Document
        ):
            return FilterResult(FilterAction.CONTINUE, message)

        doc = media.document
        old_name = filename_of(doc)
        if old_name is None:
            return FilterResult(FilterAction.CONTINUE, message)

        new_name = self._rename(old_name)
        if new_name == old_name:
            return FilterResult(FilterAction.CONTINUE, message)

        result = cached_media_result(self._cache, message)
        if result is not None:
            return result

        if doc.size > UPLOAD_LIMIT_BYTES:
            logger.info(
                "DocumentFilenameFilter: skipping rename of %.2f GB file (chat_id=%s) — "
                "exceeds the ~2GB upload limit for accounts without Telegram Premium",
                doc.size / 1024**3,
                message.chat_id,
            )
            return FilterResult(FilterAction.CONTINUE, message)

        attributes = [
            types.DocumentAttributeFilename(file_name=new_name)
            if isinstance(a, types.DocumentAttributeFilename)
            else a
            for a in doc.attributes
        ]

        uploaded = await self._reupload(message, new_name, doc, attributes)
        if uploaded is not None:
            message.media = uploaded

        return FilterResult(FilterAction.CONTINUE, message)

    @cached_reupload()
    @reupload_errors(
        fallback=None,
        media_error_fmt="DocumentFilenameFilter: download failed, mirroring original name (%s)",
        exception_fmt="DocumentFilenameFilter: rename failed (%s), sending original",
        log_arg=lambda message: private_message_link(message.chat_id, message.id),
    )
    async def _reupload(self, message, new_name, doc, attributes):
        async with downloaded_tempfile(
            message, suffix=os.path.splitext(new_name)[1]
        ) as tmp_path:
            handle = await message._client.upload_file(
                tmp_path, file_name=new_name
            )
        return types.InputMediaUploadedDocument(
            file=handle, mime_type=doc.mime_type, attributes=attributes
        )
