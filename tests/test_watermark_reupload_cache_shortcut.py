"""A second _process_message call for the same media (a second fan-out
target reusing an already-processed watermark) must short-circuit via the
top-level ReuploadCache lookup before ever invoking the decorated
_process_photo/_process_video coroutine, instead of paying for the
attribute-scan/encode-estimate pre-work again on every target and relying
solely on @cached_reupload's own internal caching."""

from datetime import datetime, timezone

from telethon import events
from telethon.tl import types

import telemirror.messagefilters.watermarkfilter as wf
from tests.conftest import make_message, run


class _Client:
    async def download_media(self, message, file):
        return b"rawphoto"

    async def upload_file(self, data, file_name=None):
        return "HANDLE"


def _photo_message(client):
    media = types.MessageMediaPhoto(
        photo=types.Photo(
            id=99, access_hash=1, file_reference=b"x",
            date=datetime.now(timezone.utc), sizes=[], dc_id=1,
        )
    )
    msg = make_message(media=media, channel_id=1000)
    msg._client = client
    return msg


def test_process_message_skips_process_photo_on_repeat_target_via_cache(monkeypatch):
    async def _stamp(data, config):
        return b"stamped"

    monkeypatch.setattr(wf, "async_stamp_watermark_on_image", _stamp)

    f = wf.WatermarkRemovalFilter()
    client = _Client()

    calls = []
    orig_process_photo = f._process_photo

    async def spy(*a, **kw):
        calls.append(1)
        return await orig_process_photo(*a, **kw)

    monkeypatch.setattr(f, "_process_photo", spy)

    run(f._process_message(_photo_message(client), events.NewMessage.Event))
    run(f._process_message(_photo_message(client), events.NewMessage.Event))

    assert len(calls) == 1
