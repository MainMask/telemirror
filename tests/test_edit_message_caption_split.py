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


class _TelegramLikeClient:
    """Rejects a >1024 caption whether or not a file is sent, and answers an
    edit that changes nothing with MessageNotModifiedError — like Telegram."""

    def __init__(self):
        self.edits = []
        self.reads = 0

    async def get_messages(self, entity, ids=None, **kw):
        self.reads += 1
        return types.Message(id=5000, peer_id=types.PeerChannel(1), message="")

    async def edit_message(self, **kw):
        self.edits.append(kw)
        if len(kw["text"]) > 1024:
            raise errors.MediaCaptionTooLongError(request=None)
        if kw["file"] is None and kw["text"] == "":
            raise errors.MessageNotModifiedError(request=None)


def test_too_long_caption_edit_without_media_change_sends_nothing_more(caplog):
    """Pass 22 self-review: with the source media unchanged (pass 22 sends no
    `file=`), re-editing the mirror with its own current caption changes
    nothing — it only drew a MessageNotModifiedError and a second WARNING to
    the tech channel on every edit of such a post."""
    client = _TelegramLikeClient()
    db = run(InMemoryDatabase())
    run(db.insert(MirrorMessage(100, SOURCE, 5000, TARGET, source_media_id=1)))
    proc = EventProcessor(
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
    msg = make_message("x" * 2000, media=_photo())  # same photo id=1
    msg.id = 100

    with caplog.at_level(logging.WARNING, logger="test.edit_caption_split"):
        run(proc.edit_message(SOURCE, msg, "link"))

    assert len(client.edits) == 1
    assert client.edits[0]["file"] is None
    assert client.reads == 0
    assert "caption too long" in caplog.text
    assert "MessageNotModifiedError" not in caplog.text


def test_deleted_mirror_gets_no_keeping_caption_warning(caplog):
    """Session-diff review: with a media change to deliver, the fallback re-reads
    the mirror first; a deleted mirror (None) must end in the ERROR alone, not
    a false "keeping the mirror's current caption" WARNING before it."""

    class _DeletedMirrorClient(_TelegramLikeClient):
        async def get_messages(self, entity, ids=None, **kw):
            self.reads += 1
            return None

    client = _DeletedMirrorClient()
    db = run(InMemoryDatabase())
    run(db.insert(MirrorMessage(100, SOURCE, 5000, TARGET, source_media_id=4)))
    proc = EventProcessor(
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
    msg = make_message("x" * 2000, media=_photo())  # photo id 1 != stored 4
    msg.id = 100

    with caplog.at_level(logging.WARNING, logger="test.edit_caption_split"):
        run(proc.edit_message(SOURCE, msg, "link"))

    assert client.reads == 1
    assert "keeping the mirror's current caption" not in caplog.text
    assert "Error while editing message" in caplog.text
