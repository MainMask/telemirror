import asyncio
import logging
import os
import tempfile
from typing import Any, Optional, Type

from telethon.tl import types

from ..hints import EventLike, EventMessage
from ..watermark.processor import (
    WatermarkConfig,
    async_remove_watermark_from_image,
    async_remove_watermark_from_video,
    async_stamp_watermark_on_image,
    async_stamp_watermark_on_video,
    estimate_stamp_encode_s,
)
from ._media import (
    UPLOAD_LIMIT_BYTES,
    ReuploadCache,
    cached_reupload,
    download_media_with_retry,
    downloaded_tempfile,
    reupload_errors,
)
from .base import FilterAction, FilterResult, MessageFilter

logger = logging.getLogger(__name__)

# Process-wide cap on concurrent ffmpeg video encodes (shared across every
# WatermarkRemovalFilter instance — settings are global, see the class
# docstring). Created lazily from the first config seen; no lock needed since
# there's no `await` between the check and the assignment, so no other
# coroutine can interleave under asyncio's single-threaded scheduling.
_video_encode_semaphore: Optional[asyncio.Semaphore] = None
_video_encode_semaphore_limit: Optional[int] = None


def _get_video_encode_semaphore(limit: int) -> asyncio.Semaphore:
    global _video_encode_semaphore, _video_encode_semaphore_limit
    if _video_encode_semaphore is None:
        _video_encode_semaphore = asyncio.Semaphore(limit)
        _video_encode_semaphore_limit = limit
    elif limit != _video_encode_semaphore_limit:
        # The cap is process-wide, not per-direction: whichever config was
        # seen first (nondeterministic — depends on message arrival order,
        # not config order) silently wins for the rest of the process unless
        # we say so here.
        logger.warning(
            "WatermarkRemovalFilter: max_concurrent_video_encodes=%s ignored — "
            "already fixed process-wide at %s by an earlier direction",
            limit, _video_encode_semaphore_limit,
        )
    return _video_encode_semaphore


class WatermarkRemovalFilter(MessageFilter):
    """Detects + inpaints a source channel's static watermark (``remove_watermark``)
    and/or stamps the own watermark (``stamp_watermark``) on photos and videos.
    Both default to true; with both false the filter is a no-op.

    Settings are global — one config for every mirrored source.

    Args:
        remove_watermark: detect + inpaint the source's watermark (needs
            ``template_path``). Default true.
        stamp_watermark: overlay ``stamp_watermark_path`` (my_watermark.png).
            Default true.
        channels: optional list of numeric source channel ids (int, or a
            numeric string) to limit processing to; omit to process every
            mirrored photo/video. Not a ``@username`` — every value is
            coerced with ``int(...)``.
        Other keys (``template_path``, ``match_threshold``, ``stamp_scale``,
        ``stamp_opacity`` …) are forwarded to WatermarkConfig.

    Example YAML config::

        - WatermarkRemovalFilter:
            remove_watermark: false   # don't touch the source's watermark
            stamp_watermark: true     # stamp my_watermark.png on everything
    """

    def __init__(
        self,
        channels: Optional[list[int]] = None,
        **config: Any,
    ) -> None:
        self._config = WatermarkConfig(**config)
        self._channels: Optional[set[int]] = (
            {int(c) for c in channels} if channels else None
        )
        # Re-send one processed upload to all fan-out targets (keyed by source id).
        self._cache = ReuploadCache()

    async def _process_message(
        self, message: EventMessage, event_type: Type[EventLike]
    ) -> FilterResult[EventMessage]:
        config = self._config
        if (
            not message.media
            or (self._channels is not None and message.chat_id not in self._channels)
            or (not config.remove_watermark and not config.stamp_watermark)
        ):
            return FilterResult(FilterAction.CONTINUE, message)

        handle = None
        if isinstance(message.media, types.MessageMediaPhoto):
            handle = await self._process_photo(message, config)
        elif isinstance(message.media, types.MessageMediaDocument):
            doc = message.media.document
            video_attr = None
            if isinstance(doc, types.Document):
                video_attr = next(
                    (
                        a
                        for a in doc.attributes
                        if isinstance(a, types.DocumentAttributeVideo)
                    ),
                    None,
                )
            max_duration = config.stamp_video_max_duration_s
            max_encode_s = config.stamp_video_max_encode_s
            est_encode_s = (
                estimate_stamp_encode_s(
                    video_attr.w or 0,
                    video_attr.h or 0,
                    video_attr.duration or 0,
                    config.stamp_video_encode_realtime_ratio,
                )
                if video_attr is not None
                else 0.0
            )
            if video_attr is not None and doc.size > UPLOAD_LIMIT_BYTES:
                logger.info(
                    "WatermarkRemovalFilter: skipping %.2f GB video (chat_id=%s) — "
                    "exceeds the ~2GB re-upload limit; forwarded as-is",
                    doc.size / 1024**3,
                    message.chat_id,
                )
            elif (
                video_attr is not None
                and max_duration > 0
                and (video_attr.duration or 0) > max_duration
            ):
                logger.info(
                    "WatermarkRemovalFilter: %.0fs video exceeds the %.0fs re-encode "
                    "limit (chat_id=%s) — forwarded as-is without watermark",
                    video_attr.duration,
                    max_duration,
                    message.chat_id,
                )
            elif (
                video_attr is not None
                and max_encode_s > 0
                and est_encode_s > max_encode_s
            ):
                logger.info(
                    "WatermarkRemovalFilter: %dx%d %.0fs video — predicted re-encode "
                    "≈%.0fs over the %.0fs budget (chat_id=%s) — forwarded as-is "
                    "without watermark",
                    video_attr.w or 0,
                    video_attr.h or 0,
                    video_attr.duration or 0,
                    est_encode_s,
                    max_encode_s,
                    message.chat_id,
                )
            elif video_attr is not None:
                handle = await self._process_video(message, config, doc)
        elif isinstance(
            message.media,
            (types.InputMediaUploadedPhoto, types.InputMediaUploadedDocument),
        ):
            # An earlier filter (e.g. RestrictSavingContentBypassFilter) already
            # rewrote message.media into an upload handle — there are no raw
            # bytes left here to watermark, so log rather than silently no-op.
            logger.warning(
                "WatermarkRemovalFilter: media already re-uploaded by an earlier "
                "filter, skipping watermark (chat_id=%s)",
                message.chat_id,
            )

        if handle is not None:
            message.media = handle

        return FilterResult(FilterAction.CONTINUE, message)

    @cached_reupload()
    @reupload_errors(
        fallback=None,
        media_error_fmt="WatermarkRemovalFilter: download failed, mirroring original photo (chat_id=%s)",
        exception_fmt="WatermarkRemovalFilter: photo processing failed (chat_id=%s)",
    )
    async def _process_photo(
        self,
        message: EventMessage,
        config: WatermarkConfig,
    ):
        """Return the re-uploaded file handle, or None on failure."""
        photo_bytes: bytes = await download_media_with_retry(message, file=bytes)
        cleaned = (
            await async_remove_watermark_from_image(photo_bytes, config)
            if config.remove_watermark
            else None
        )
        output: Optional[bytes]
        if config.stamp_watermark:
            output = await async_stamp_watermark_on_image(
                cleaned if cleaned is not None else photo_bytes, config
            )
        else:
            output = cleaned  # nothing to re-upload unless removal changed it
        if output is None:
            return None
        return await message._client.upload_file(output, file_name="photo.jpg")

    @cached_reupload()
    @reupload_errors(
        fallback=None,
        media_error_fmt="WatermarkRemovalFilter: download failed, mirroring original video (chat_id=%s)",
        exception_fmt="WatermarkRemovalFilter: video processing failed (chat_id=%s)",
    )
    async def _process_video(
        self,
        message: EventMessage,
        config: WatermarkConfig,
        doc: types.Document,
    ):
        """Return the re-uploaded media, or None if nothing was produced."""
        tmp_out = tmp_stamp = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix="telemirror-tmp-", suffix=".mp4", delete=False
            ) as f:
                tmp_out = f.name
            with tempfile.NamedTemporaryFile(
                prefix="telemirror-tmp-", suffix=".mp4", delete=False
            ) as f:
                tmp_stamp = f.name

            async with downloaded_tempfile(message, suffix=".mp4") as tmp_in:
                semaphore = _get_video_encode_semaphore(config.max_concurrent_video_encodes)
                async with semaphore:
                    removed = (
                        await async_remove_watermark_from_video(tmp_in, config, tmp_out)
                        if config.remove_watermark
                        else False
                    )
                    source_for_stamp = tmp_out if removed else tmp_in
                    stamped = (
                        await async_stamp_watermark_on_video(source_for_stamp, config, tmp_stamp)
                        if config.stamp_watermark
                        else False
                    )

            upload_path = tmp_stamp if stamped else (tmp_out if removed else None)
            if upload_path is not None:
                handle = await message._client.upload_file(upload_path)
                # A bare upload handle carries no metadata, so Telethon's own
                # attribute inference can't recover it — it would (re-)guess a
                # generic DocumentAttributeVideo and never add
                # DocumentAttributeAnimated, turning a mirrored Telegram "GIF"
                # into a plain video. Re-declare the source doc's attributes
                # explicitly instead (same pattern as
                # RestrictSavingContentBypassFilter._process_document).
                return types.InputMediaUploadedDocument(
                    file=handle, mime_type=doc.mime_type, attributes=doc.attributes
                )
            return None
        finally:
            for p in (tmp_out, tmp_stamp):
                if p and os.path.exists(p):
                    os.unlink(p)
