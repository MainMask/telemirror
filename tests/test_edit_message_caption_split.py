"""A mirror whose too-long caption was split at send time (media with an empty
caption + an untracked text reply) can't take the full edited caption back:
Telegram answers MediaCaptionTooLongError. The edit must then still reach the
media (empty caption, same as sent) and log a WARNING, not fail with an ERROR
on every edit of such a post (Pass 21)."""

import logging

from telethon import errors
from telethon.tl import types

from config import DirectionConfig
from telemirror.messagefilters import EmptyMessageFilter
from telemirror.mirroring import EventProcessor
from telemirror.storage import InMemoryDatabase, MirrorMessage
from tests.conftest import make_message, run

SOURCE = -1001000000000
TARGET = -1002000000001


class _CaptionLimitClient:
    """Rejects any caption over 1024 chars, like a non-Premium account, and
    serves the mirror's current caption (``""`` for a split-at-send mirror)."""

    def __init__(self, current_caption=""):
        self.edits = []
        self._current = types.Message(
            id=5000, peer_id=types.PeerChannel(2000000001),
            message=current_caption,
            entities=[types.MessageEntityBold(offset=0, length=3)] if current_caption else None,
        )

    async def get_messages(self, entity, ids=None, **kw):
        return self._current

    async def edit_message(self, **kw):
        self.edits.append(kw)
        if kw["file"] is not None and len(kw["text"]) > 1024:
            raise errors.MediaCaptionTooLongError(request=None)


def _photo():
    return types.MessageMediaPhoto(
        photo=types.Photo(
            id=1, access_hash=1, file_reference=b"", date=None, sizes=[], dc_id=2
        )
    )


def _processor(client):
    db = run(InMemoryDatabase())
    run(db.insert(MirrorMessage(100, SOURCE, 5000, TARGET)))
    return EventProcessor(
        chat_mapping={
            SOURCE: {
                TARGET: [
                    DirectionConfig(
                        disable_delete=False, disable_edit=False,
                        filters=EmptyMessageFilter(),
                    )
                ]
            }
        },
        database=db,
        client=client,
        logger=logging.getLogger("test.edit_caption_split"),
    )


def test_split_caption_edit_retries_without_caption(caplog):
    client = _CaptionLimitClient()
    proc = _processor(client)
    msg = make_message("x" * 2000, media=_photo())
    msg.id = 100

    with caplog.at_level(logging.WARNING, logger="test.edit_caption_split"):
        run(proc.edit_message(SOURCE, msg, "link"))

    assert len(client.edits) == 2
    retry = client.edits[1]
    assert retry["text"] == ""
    assert retry["formatting_entities"] == []
    assert isinstance(retry["file"], types.MessageMediaPhoto)  # media still edited
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert any("caption" in r.getMessage() for r in caplog.records)


def test_unsplit_mirror_keeps_its_caption_when_the_source_outgrows_the_limit():
    """The mirror was sent with its whole (<=1024) caption, then the source
    caption was edited past the limit: the fallback must keep the mirror's
    current caption (and still update the media), not wipe it to ``""``."""
    client = _CaptionLimitClient(current_caption="old caption")
    proc = _processor(client)
    msg = make_message("x" * 2000, media=_photo())
    msg.id = 100

    run(proc.edit_message(SOURCE, msg, "link"))

    assert len(client.edits) == 2
    retry = client.edits[1]
    assert retry["text"] == "old caption"
    assert retry["formatting_entities"] == [types.MessageEntityBold(offset=0, length=3)]
    assert isinstance(retry["file"], types.MessageMediaPhoto)
