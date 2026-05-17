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
)
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

    async def _process_message(
        self, message: EventMessage, event_type: Type[EventLike]
    ) -> FilterResult[EventMessage]:
        config = self._configs.get(message.chat_id)
        if config is None or not message.media:
            return FilterResult(FilterAction.CONTINUE, message)

        if isinstance(message.media, types.MessageMediaPhoto):
            await self._process_photo(message, config)
        elif isinstance(message.media, types.MessageMediaDocument):
            doc = message.media.document
            if isinstance(doc, types.Document) and any(
                isinstance(a, types.DocumentAttributeVideo) for a in doc.attributes
            ):
                await self._process_video(message, config)

        return FilterResult(FilterAction.CONTINUE, message)

    async def _process_photo(
        self,
        message: EventMessage,
        config: ChannelWatermarkConfig,
    ) -> None:
        try:
            photo_bytes: bytes = await message._client.download_media(
                message=message, file=bytes
            )
            cleaned = await async_remove_watermark_from_image(photo_bytes, config)
            if cleaned is not None:
                handle = await message._client.upload_file(cleaned)
                message.media = handle
        except Exception:
            logger.exception(
                "WatermarkRemovalFilter: photo processing failed (chat_id=%s)", message.chat_id
            )

    async def _process_video(
        self,
        message: EventMessage,
        config: ChannelWatermarkConfig,
    ) -> None:
        tmp_in = tmp_out = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
                tmp_in = f.name
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
                tmp_out = f.name

            await message._client.download_media(message=message, file=tmp_in)
            removed = await async_remove_watermark_from_video(tmp_in, config, tmp_out)
            if removed:
                handle = await message._client.upload_file(tmp_out)
                message.media = handle
        except Exception:
            logger.exception(
                "WatermarkRemovalFilter: video processing failed (chat_id=%s)", message.chat_id
            )
        finally:
            for p in (tmp_in, tmp_out):
                if p and os.path.exists(p):
                    os.unlink(p)
