"""A second `_process_message` call for the same noforwards-protected photo
(a second fan-out target reusing an already-reuploaded photo) must
short-circuit via the top-level ReuploadCache lookup before ever invoking
the decorated `_reupload` coroutine, instead of paying for the isinstance/
size-check pre-work again on every target and relying solely on
`@cached_reupload`'s own internal caching -- the same shortcut
WatermarkRemovalFilter/DocumentFilenameFilter already get."""

from datetime import datetime, timezone

from telethon import events
from telethon.tl import types

from telemirror.messagefilters.restrictsavingfilter import (
    RestrictSavingContentBypassFilter,
)
from tests.conftest import make_message, run


class _NoForwards:
    noforwards = True


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
    msg = make_message(media=media)
    msg._chat = _NoForwards()
    msg._client = client
    return msg


def test_process_message_skips_reupload_on_repeat_target_via_cache(monkeypatch):
    f = RestrictSavingContentBypassFilter()
    client = _Client()

    calls = []
    orig_reupload = f._reupload

    async def spy(*a, **kw):
        calls.append(1)
        return await orig_reupload(*a, **kw)

    monkeypatch.setattr(f, "_reupload", spy)

    run(f._process_message(_photo_message(client), events.NewMessage.Event))
    run(f._process_message(_photo_message(client), events.NewMessage.Event))

    assert len(calls) == 1
