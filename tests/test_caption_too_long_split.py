"""Regression: on the MediaCaptionTooLongError split path, a media message that
was actually delivered must be tracked in the DB immediately — before the
follow-up text send is even attempted — so a crash during a long tail retry
can never make past_mode resend the media.

Also: a FloodWait raised while (re)sending the *media* on that split path must
propagate (past_mode retries without advancing the checkpoint), whereas a
FloodWait on the *text tail* is waited out and retried in place (the media is
already tracked by then, so retrying can't cause a duplicate) — only a
recurring FloodWait that outlasts the retry budget loses the tail text."""

import logging

import pytest
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


@pytest.mark.parametrize(
    "exc",
    [mirroring.errors.FloodWaitError, mirroring.errors.FloodPremiumWaitError],
)
def test_new_message_flood_on_media_retry_propagates(monkeypatch, exc):
    db = run(InMemoryDatabase())
    calls = []

    async def fake_send_message(client, entity, message, **kw):
        calls.append(message)
        if len(calls) == 1:  # first attempt with caption
            raise mirroring.errors.MediaCaptionTooLongError(request=None)
        raise exc(request=None)  # media-only retry floods

    monkeypatch.setattr(mirroring, "send_message", fake_send_message)

    msg = make_message("x" * 1100, media=types.MessageMediaUnsupported(), channel_id=1000)
    with pytest.raises(exc):
        run(_proc(db).new_message(SOURCE, msg, "link"))

    assert run(db.get_messages(msg.id, SOURCE)) == []


@pytest.mark.parametrize(
    "exc",
    [mirroring.errors.FloodWaitError, mirroring.errors.FloodPremiumWaitError],
)
def test_new_message_flood_on_text_tail_gives_up_after_retries(monkeypatch, exc):
    """A FloodWait that never clears on the text tail is retried up to
    `_TAIL_SEND_FLOOD_RETRY_LIMIT` times (harmless here: `exc(request=None)`
    carries a 0-second wait), then finally gives up — losing only the text,
    since the media was already tracked before the first tail attempt."""
    db = run(InMemoryDatabase())
    calls = []

    async def fake_send_message(client, entity, message, **kw):
        calls.append(message)
        if len(calls) == 1:
            raise mirroring.errors.MediaCaptionTooLongError(request=None)
        if len(calls) == 2:  # media-only retry succeeds
            return types.Message(id=778, peer_id=types.PeerChannel(1), message="")
        raise exc(request=None)  # text tail keeps flooding — tail is allowed to be lost

    monkeypatch.setattr(mirroring, "send_message", fake_send_message)

    msg = make_message("x" * 1100, media=types.MessageMediaUnsupported(), channel_id=1000)
    run(_proc(db).new_message(SOURCE, msg, "link"))

    assert [m.mirror_id for m in run(db.get_messages(msg.id, SOURCE))] == [778]
    # 1 (caption-too-long) + 1 (media retry) + (limit + 1) tail attempts
    assert len(calls) == 2 + mirroring._TAIL_SEND_FLOOD_RETRY_LIMIT + 1


def test_new_message_flood_on_text_tail_recovers(monkeypatch):
    """A transient FloodWait on the text tail must not lose the text: once the
    wait clears, the retry loop delivers it."""
    db = run(InMemoryDatabase())
    calls = []

    async def fake_send_message(client, entity, message, **kw):
        calls.append(message)
        if len(calls) == 1:
            raise mirroring.errors.MediaCaptionTooLongError(request=None)
        if len(calls) == 2:  # media-only retry succeeds
            return types.Message(id=779, peer_id=types.PeerChannel(1), message="")
        if len(calls) in (3, 4):  # tail floods twice, then recovers
            raise mirroring.errors.FloodWaitError(request=None)
        return types.Message(id=780, peer_id=types.PeerChannel(1), message="")

    monkeypatch.setattr(mirroring, "send_message", fake_send_message)

    long_caption = "x" * 1100
    msg = make_message(long_caption, media=types.MessageMediaUnsupported(), channel_id=1000)
    run(_proc(db).new_message(SOURCE, msg, "link"))

    assert len(calls) == 5
    assert calls[-1] == long_caption  # the tail text was actually delivered
    assert [m.mirror_id for m in run(db.get_messages(msg.id, SOURCE))] == [779]


@pytest.mark.parametrize(
    "exc",
    [mirroring.errors.FloodWaitError, mirroring.errors.FloodPremiumWaitError],
)
def test_new_album_flood_on_media_retry_propagates(monkeypatch, exc):
    db = run(InMemoryDatabase())
    send_file_calls = []

    async def fake_send_file(client, entity, caption, file, **kw):
        send_file_calls.append(caption)
        if len(send_file_calls) == 1:
            raise mirroring.errors.MediaCaptionTooLongError(request=None)
        raise exc(request=None)  # split-caption retry floods

    monkeypatch.setattr(mirroring, "send_file", fake_send_file)

    album = [
        make_message("x" * 1100, media=types.MessageMediaUnsupported(), channel_id=1000),
        make_message("y", media=types.MessageMediaUnsupported(), channel_id=1000),
    ]
    album[1].id = 2
    with pytest.raises(exc):
        run(_proc(db).new_album(SOURCE, album, "link"))

    assert run(db.get_messages(1, SOURCE)) == []
    assert run(db.get_messages(2, SOURCE)) == []


def test_new_album_flood_on_caption_tail_recovers(monkeypatch):
    """Same recovery guarantee as new_message: a transient FloodWait on the
    album's caption tail must not lose the text once the wait clears."""
    db = run(InMemoryDatabase())
    send_file_calls = []
    send_message_calls = []

    async def fake_send_file(client, entity, caption, file, **kw):
        send_file_calls.append(caption)
        if len(send_file_calls) == 1:
            raise mirroring.errors.MediaCaptionTooLongError(request=None)
        return [
            types.Message(id=911, peer_id=types.PeerChannel(1), message=""),
            types.Message(id=912, peer_id=types.PeerChannel(1), message=""),
        ]

    async def fake_send_message(client, entity, message, **kw):
        send_message_calls.append(message)
        if len(send_message_calls) == 1:
            raise mirroring.errors.FloodWaitError(request=None)
        return types.Message(id=913, peer_id=types.PeerChannel(1), message="")

    monkeypatch.setattr(mirroring, "send_file", fake_send_file)
    monkeypatch.setattr(mirroring, "send_message", fake_send_message)

    long_caption = "x" * 1100
    album = [
        make_message(long_caption, media=types.MessageMediaUnsupported(), channel_id=1000),
        make_message("y", media=types.MessageMediaUnsupported(), channel_id=1000),
    ]
    album[1].id = 2
    run(_proc(db).new_album(SOURCE, album, "link"))

    assert len(send_message_calls) == 2
    assert send_message_calls[-1] == long_caption  # the caption tail was delivered
    tracked = run(db.get_messages(1, SOURCE)) + run(db.get_messages(2, SOURCE))
    assert sorted(m.mirror_id for m in tracked) == [911, 912]
