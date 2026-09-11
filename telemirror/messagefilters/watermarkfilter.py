import logging
import os
import tempfile
from typing import Dict, Type

from telethon.tl import types

from ..hints import EventLike, EventMessage
from ..watermark.processor import (
    ChannelWatermarkConfig,
    async_remove_watermark_from_image,
    async_remove_watermark_from_video,
    async_stamp_watermark_on_image,
    async_stamp_watermark_on_video,
)
from ._media import UPLOAD_LIMIT_BYTES, ReuploadCache, source_media_id
from .base import FilterAction, FilterResult, MessageFilter

logger = logging.getLogger(__name__)


class WatermarkRemovalFilter(MessageFilter):
    """Removes static channel watermarks from photos and videos before forwarding.

    Args:
        channels: Per-channel config keyed by channel ID (int or str).
            Each value is a dict passed to ChannelWatermarkConfig — at minimum
            requires ``template_path``.

    Example YAML config::

        - WatermarkRemovalFilter:
            channels:
              -1001585626790:
                template_path: "/data/watermarks/channel_a.png"
                match_threshold: 0.75
    """

    def __init__(self, channels: Dict[int | str, dict]) -> None:
        self._configs: Dict[int, ChannelWatermarkConfig] = {
            int(k): ChannelWatermarkConfig(**v) for k, v in channels.items()
        }
        # Re-send one processed upload to all fan-out targets (keyed by source id).
        self._cache = ReuploadCache()

    async def _process_message(
        self, message: EventMessage, event_type: Type[EventLike]
    ) -> FilterResult[EventMessage]:
        config = self._configs.get(message.chat_id)
        if config is None or not message.media:
            return FilterResult(FilterAction.CONTINUE, message)

        key = source_media_id(message.media)
        if key is not None:
            cached = self._cache.get(key)
            if cached is not None:
                message.media = cached
                return FilterResult(FilterAction.CONTINUE, message)

        handle = None
        if isinstance(message.media, types.MessageMediaPhoto):
            handle = await self._process_photo(message, config)
        elif isinstance(message.media, types.MessageMediaDocument):
            doc = message.media.document
            is_video = isinstance(doc, types.Document) and any(
                isinstance(a, types.DocumentAttributeVideo) for a in doc.attributes
            )
            if is_video and doc.size > UPLOAD_LIMIT_BYTES:
                logger.info(
                    "WatermarkRemovalFilter: skipping %.2f GB video (chat_id=%s) — "
                    "exceeds the ~2GB re-upload limit; forwarded as-is",
                    doc.size / 1024**3,
                    message.chat_id,
                )
            elif is_video:
                handle = await self._process_video(message, config)

        if handle is not None:
            message.media = handle
            if key is not None:
                self._cache.put(key, handle)

        return FilterResult(FilterAction.CONTINUE, message)

    async def _process_photo(
        self,
        message: EventMessage,
        config: ChannelWatermarkConfig,
    ):
        """Return the re-uploaded file handle, or None on failure."""
        try:
            photo_bytes: bytes = await message._client.download_media(
                message=message, file=bytes
            )
            cleaned = await async_remove_watermark_from_image(photo_bytes, config)
            stamped = await async_stamp_watermark_on_image(
                cleaned if cleaned is not None else photo_bytes, config
            )
            return await message._client.upload_file(stamped, file_name="photo.jpg")
        except Exception:
            logger.exception(
                "WatermarkRemovalFilter: photo processing failed (chat_id=%s)", message.chat_id
            )
            return None

    async def _process_video(
        self,
        message: EventMessage,
        config: ChannelWatermarkConfig,
    ):
        """Return the re-uploaded file handle, or None if nothing was produced."""
        tmp_in = tmp_out = tmp_stamp = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
                tmp_in = f.name
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
                tmp_out = f.name
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
                tmp_stamp = f.name

            await message._client.download_media(message=message, file=tmp_in)
            removed = await async_remove_watermark_from_video(tmp_in, config, tmp_out)
            source_for_stamp = tmp_out if removed else tmp_in
            stamped = await async_stamp_watermark_on_video(source_for_stamp, config, tmp_stamp)

            upload_path = tmp_stamp if stamped else (tmp_out if removed else None)
            if upload_path is not None:
                return await message._client.upload_file(upload_path)
            return None
        except Exception:
            logger.exception(
                "WatermarkRemovalFilter: video processing failed (chat_id=%s)", message.chat_id
            )
            return None
        finally:
            for p in (tmp_in, tmp_out, tmp_stamp):
                if p and os.path.exists(p):
                    os.unlink(p)
