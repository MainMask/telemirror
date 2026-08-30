"""Regression: on the MediaCaptionTooLongError split path, a media message that
was actually delivered must be tracked in the DB even when the follow-up text
send fails (only the text tail is allowed to be lost)."""

import logging

from telethon.tl import types

import telemirror.mirroring as mirroring
from config import DirectionConfig
from telemirror.messagefilters import EmptyMessageFilter
from telemirror.mirroring import EventProcessor
from telemirror.storage import InMemoryDatabase
from tests.conftest import make_message, run

SOURCE = -1001000000000
TARGET = -1002000000001


def _cfg():
    return DirectionConfig(
        disable_delete=False, disable_edit=False, filters=EmptyMessageFilter()
    )


def _proc(db):
    return EventProcessor(
        chat_mapping={SOURCE: {TARGET: [_cfg()]}},
        database=db,
        client=object(),
        logger=logging.getLogger("test.split"),
    )


def test_new_message_tracks_media_when_text_tail_fails(monkeypatch):
    db = run(InMemoryDatabase())
    calls = []

    async def fake_send_message(client, entity, message, **kw):
        calls.append(message)
        if len(calls) == 1:  # first attempt with caption
            raise mirroring.errors.MediaCaptionTooLongError(request=None)
        if len(calls) == 2:  # media-only retry succeeds
            return types.Message(id=777, peer_id=types.PeerChannel(1), message="")
        raise RuntimeError("text tail send failed")  # follow-up text

    monkeypatch.setattr(mirroring, "send_message", fake_send_message)

    msg = make_message("x" * 1100, media=types.MessageMediaUnsupported(), channel_id=1000)
    run(_proc(db).new_message(SOURCE, msg, "link"))

    tracked = run(db.get_messages(msg.id, SOURCE))
    assert [m.mirror_id for m in tracked] == [777]


def test_new_album_tracks_media_when_caption_tail_fails(monkeypatch):
    db = run(InMemoryDatabase())
    send_file_calls = []

    async def fake_send_file(client, entity, caption, file, **kw):
        send_file_calls.append(caption)
        if len(send_file_calls) == 1:
            raise mirroring.errors.MediaCaptionTooLongError(request=None)
        return [
            types.Message(id=901, peer_id=types.PeerChannel(1), message=""),
            types.Message(id=902, peer_id=types.PeerChannel(1), message=""),
        ]

    async def fake_send_message(client, entity, message, **kw):
        raise RuntimeError("caption tail send failed")

    monkeypatch.setattr(mirroring, "send_file", fake_send_file)
    monkeypatch.setattr(mirroring, "send_message", fake_send_message)

    album = [
        make_message("x" * 1100, media=types.MessageMediaUnsupported(), channel_id=1000),
        make_message("y", media=types.MessageMediaUnsupported(), channel_id=1000),
    ]
    album[1].id = 2
    run(_proc(db).new_album(SOURCE, album, "link"))

    tracked = run(db.get_messages(1, SOURCE)) + run(db.get_messages(2, SOURCE))
    assert sorted(m.mirror_id for m in tracked) == [901, 902]
