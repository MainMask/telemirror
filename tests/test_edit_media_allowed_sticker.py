"""edit_message must not pass a sticker's media into client.edit_message
(`file=...`) — Telethon rejects replacing an existing message's media with a
sticker (or a voice note) with MediaPrevInvalidError, so edit_media_allowed
must treat both the same way: text-only edit (file=None)."""

import logging

from telethon.tl import types

from config import DirectionConfig
from telemirror.messagefilters import EmptyMessageFilter
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
