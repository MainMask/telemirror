import logging
import os
import re
from typing import Optional, Type

from telethon.tl import types

from ..hints import EventLike, EventMessage
from ._media import (
    UPLOAD_LIMIT_BYTES,
    ReuploadCache,
    downloaded_tempfile,
    filename_of,
)
from .base import FilterAction, FilterResult, MessageFilter

logger = logging.getLogger(__name__)


class DocumentFilenameFilter(MessageFilter):
    """Rewrites the filename of mirrored documents.

    Prepends ``prefix`` and removes unwanted substrings (case-insensitive).
    Only documents that carry a ``DocumentAttributeFilename`` are affected;
    voice notes, photos, stickers and GIFs have no filename and pass through.

    Place after `RestrictSavingContentBypassFilter`: for a `noforwards` source
    that filter already re-uploads the file, so this one only patches the
    filename attribute in place. For a plain reference document it downloads
    and re-uploads the file with the new name (once per file, cached across a
    broadcast fan-out).

    Args:
        prefix (str): text prepended as ``{prefix} - {name}``.
        remove (list[str]): substrings stripped from the filename.
    """

    def __init__(
        self, prefix: str = "", remove: Optional[list[str]] = None
    ) -> None:
        self._prefix = prefix
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

        if self._prefix and (
            stem == self._prefix or stem.startswith(f"{self._prefix} - ")
        ):
            return name

        if self._remove_regex is not None:
            stem = self._remove_regex.sub("", stem).strip(" _-")

        if self._prefix:
            stem = f"{self._prefix} - {stem}" if stem else self._prefix

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

        cached = self._cache.get(doc.id)
        if cached is not None:
            message.media = cached
            return FilterResult(FilterAction.CONTINUE, message)

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

        try:
            async with downloaded_tempfile(
                message, suffix=os.path.splitext(new_name)[1]
            ) as tmp_path:
                handle = await message._client.upload_file(
                    tmp_path, file_name=new_name
                )
            uploaded = types.InputMediaUploadedDocument(
                file=handle, mime_type=doc.mime_type, attributes=attributes
            )
            message.media = uploaded
            # An upload handle can be re-sent to several chats, so a broadcast
            # fan-out reuses it instead of re-uploading once per target.
            self._cache.put(doc.id, uploaded)
        except Exception:
            logger.exception(
                "DocumentFilenameFilter: rename failed (chat_id=%s), sending original",
                message.chat_id,
            )

        return FilterResult(FilterAction.CONTINUE, message)
