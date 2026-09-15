"""A >threshold FloodWait during WatermarkRemovalFilter's re-upload must
propagate (so past_mode's retry wrapper sees it), not be swallowed by the
filter's own generic except — same contract as RestrictSavingContentBypassFilter
(see test_restrict_saving_filter.py)."""

from datetime import datetime, timezone

import pytest
from telethon import errors
from telethon.tl import types

from telemirror.messagefilters import WatermarkRemovalFilter
from tests.conftest import make_message, run


class _FloodClient:
    async def download_media(self, message, file):
        raise errors.FloodWaitError(request=None)


def _photo_message(client):
    media = types.MessageMediaPhoto(
        photo=types.Photo(
            id=1, access_hash=1, file_reference=b"x",
            date=datetime.now(timezone.utc), sizes=[], dc_id=1,
        )
    )
    msg = make_message("", media=media, channel_id=1000)
    msg._client = client
    return msg


def test_photo_flood_during_reupload_propagates():
    f = WatermarkRemovalFilter()
    with pytest.raises(errors.FloodWaitError):
        run(f._process_photo(_photo_message(_FloodClient()), f._config))


def test_already_reuploaded_media_is_left_alone_and_logged(caplog):
    """If an earlier filter (e.g. RestrictSavingContentBypassFilter) already
    rewrote message.media into an upload handle, there are no raw bytes left
    to watermark — it must be a logged no-op, not a silent one."""
    from telethon import events

    f = WatermarkRemovalFilter()
    handle = types.InputMediaUploadedPhoto(file=object())
    msg = make_message("", media=handle, channel_id=1000)

    with caplog.at_level("WARNING"):
        action, result = run(f._process_message(msg, events.NewMessage.Event))

    assert result.media is handle  # unchanged
    assert any("already re-uploaded" in r.message for r in caplog.records)
