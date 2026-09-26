"""edit_message must not pass a sticker's media into client.edit_message
(`file=...`) — Telethon rejects replacing an existing message's media with a
sticker (or a voice note) with MediaPrevInvalidError, so edit_media_allowed
must treat both the same way: text-only edit (file=None)."""

import logging
from types import SimpleNamespace

import pytest
from telethon.tl import types

from config import DirectionConfig
from telemirror.messagefilters import (
    EmptyMessageFilter,
    RestrictSavingContentBypassFilter,
)
from telemirror.mirroring import EventProcessor
from telemirror.storage import InMemoryDatabase, MirrorMessage
from tests.conftest import make_message, run

SOURCE = -1001000000000
TARGET = -1002000000001


def _sticker_media() -> types.MessageMediaDocument:
    return types.MessageMediaDocument(
        document=types.Document(
            id=42, access_hash=0, file_reference=b"ref", date=None,
            mime_type="image/webp", size=1024, dc_id=1,
            attributes=[
                types.DocumentAttributeSticker(
                    alt="", stickerset=types.InputStickerSetEmpty()
                )
            ],
        )
    )


class _FakeClient:
    def __init__(self):
        self.edit_calls = []

    async def edit_message(self, entity, message, file=None, **kw):
        self.edit_calls.append(file)


def test_edit_media_allowed_is_false_for_sticker():
    db = run(InMemoryDatabase())
    run(db.insert_batch([MirrorMessage(1, SOURCE, 900, TARGET)]))

    client = _FakeClient()
    cfg = DirectionConfig(
        disable_delete=False, disable_edit=False, filters=EmptyMessageFilter()
    )
    proc = EventProcessor(
        chat_mapping={SOURCE: {TARGET: [cfg]}},
        database=db,
        client=client,
        logger=logging.getLogger("test.editsticker"),
    )

    msg = make_message(media=_sticker_media(), channel_id=1000)
    msg.id = 1
    msg._client = client

    run(proc.edit_message(SOURCE, msg, "link"))

    assert client.edit_calls == [None]


def _voice_media() -> types.MessageMediaDocument:
    return types.MessageMediaDocument(
        document=types.Document(
            id=43, access_hash=0, file_reference=b"ref", date=None,
            mime_type="audio/ogg", size=1024, dc_id=1,
            attributes=[types.DocumentAttributeAudio(duration=3, voice=True)],
        )
    )


class _ReuploadingClient(_FakeClient):
    def __init__(self):
        super().__init__()
        self.downloads = 0

    async def download_media(self, message, file=None, **kw):
        self.downloads += 1
        return b"x"

    async def upload_file(self, f, file_name=None, **kw):
        return types.InputFile(id=1, parts=1, name=file_name or "f", md5_checksum="")


@pytest.mark.parametrize("media", [_sticker_media, _voice_media])
def test_noforwards_voice_or_sticker_is_not_reuploaded_into_the_edit(media):
    """Pass 22: RestrictSavingContentBypassFilter turned a noforwards source's
    voice note/sticker into InputMediaUploadedDocument, the guard (which
    looked at the filtered media) missed it and `file=` was sent — Telegram
    rejects that with MediaPrevInvalidError, losing the caption edit. The
    kind is now judged on the source, and the media isn't downloaded at all."""
    db = run(InMemoryDatabase())
    run(db.insert_batch([MirrorMessage(1, SOURCE, 900, TARGET)]))

    client = _ReuploadingClient()
    cfg = DirectionConfig(
        disable_delete=False,
        disable_edit=False,
        filters=RestrictSavingContentBypassFilter(),
    )
    proc = EventProcessor(
        chat_mapping={SOURCE: {TARGET: [cfg]}},
        database=db,
        client=client,
        logger=logging.getLogger("test.editsticker"),
    )

    msg = make_message("caption", media=media(), channel_id=1000)
    msg.id = 1
    msg._client = client
    msg._chat = SimpleNamespace(noforwards=True)

    run(proc.edit_message(SOURCE, msg, "link"))

    assert client.edit_calls == [None]
    assert client.downloads == 0
