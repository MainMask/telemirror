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


def test_new_album_caption_tail_skips_gracefully_on_short_send_response(monkeypatch):
    """If the album send returns fewer messages than were sent (the same
    "count mismatch" case `track_media` already treats as reachable and
    guards for its own DB insert), a caption-tail text for an album item
    beyond the truncated response must be logged and skipped, not index past
    the end of `outgoing_messages` and crash the whole target's send."""
    db = run(InMemoryDatabase())
    send_file_calls = []

    async def fake_send_file(client, entity, caption, file, **kw):
        send_file_calls.append(caption)
        if len(send_file_calls) == 1:
            raise mirroring.errors.MediaCaptionTooLongError(request=None)
        # Only 1 message for a 2-item album: item index 1 (the one with the
        # overflowing caption) has no corresponding sent message.
        return [types.Message(id=941, peer_id=types.PeerChannel(1), message="")]

    monkeypatch.setattr(mirroring, "send_file", fake_send_file)

    long_caption = "x" * 1100
    album = [
        make_message("a", media=types.MessageMediaUnsupported(), channel_id=1000),
        make_message(long_caption, media=types.MessageMediaUnsupported(), channel_id=1000),
    ]
    album[1].id = 2
    run(_proc(db).new_album(SOURCE, album, "link"))  # must not raise IndexError


def test_new_album_caption_tail_replies_to_correct_album_item(monkeypatch):
    """The caption-tail text for an over-1024-char caption must reply to the
    album item whose own caption actually overflowed, not always item 0."""
    db = run(InMemoryDatabase())
    send_file_calls = []
    reply_to_ids = []

    async def fake_send_file(client, entity, caption, file, **kw):
        send_file_calls.append(caption)
        if len(send_file_calls) == 1:
            raise mirroring.errors.MediaCaptionTooLongError(request=None)
        return [
            types.Message(id=931, peer_id=types.PeerChannel(1), message=""),
            types.Message(id=932, peer_id=types.PeerChannel(1), message=""),
            types.Message(id=933, peer_id=types.PeerChannel(1), message=""),
        ]

    async def fake_send_message(client, entity, message, **kw):
        reply_to_ids.append(kw.get("reply_to"))
        return types.Message(id=934, peer_id=types.PeerChannel(1), message="")

    monkeypatch.setattr(mirroring, "send_file", fake_send_file)
    monkeypatch.setattr(mirroring, "send_message", fake_send_message)

    long_caption = "x" * 1100
    album = [
        make_message("a", media=types.MessageMediaUnsupported(), channel_id=1000),
        make_message(long_caption, media=types.MessageMediaUnsupported(), channel_id=1000),
        make_message("c", media=types.MessageMediaUnsupported(), channel_id=1000),
    ]
    album[1].id = 2
    album[2].id = 3
    run(_proc(db).new_album(SOURCE, album, "link"))

    # Item index 1's overflowing caption must reply to outgoing_messages[1] (932),
    # not outgoing_messages[0] (931).
    assert reply_to_ids == [932]


def test_new_album_split_measures_caption_in_utf16_not_codepoints(monkeypatch):
    """`_send_album_with_caption_split`'s per-item 1024 check must use
    Telegram's UTF-16 code-unit length, not Python's codepoint `len()`. An
    emoji-heavy caption can be <=1024 Python chars while its real (UTF-16)
    length exceeds 1024 — surrogate pairs count as 2 units each. Emulates
    Telegram's own send_file by raising MediaCaptionTooLongError whenever any
    caption's *UTF-16* length is over the limit, exactly like the real
    server would (regardless of what our own split logic decided)."""
    from telethon import utils as tg_utils

    db = run(InMemoryDatabase())
    send_file_calls = []
    send_message_calls = []

    # 600 non-BMP emoji: 600 Python chars, but 1200 UTF-16 code units.
    emoji_caption = "\U0001F600" * 600

    async def fake_send_file(client, entity, caption, file, **kw):
        send_file_calls.append(list(caption))
        if any(len(tg_utils.add_surrogate(c)) > 1024 for c in caption):
            raise mirroring.errors.MediaCaptionTooLongError(request=None)
        return [
            types.Message(id=921, peer_id=types.PeerChannel(1), message=""),
            types.Message(id=922, peer_id=types.PeerChannel(1), message=""),
        ]

    async def fake_send_message(client, entity, message, **kw):
        send_message_calls.append(message)
        return types.Message(id=923, peer_id=types.PeerChannel(1), message="")

    monkeypatch.setattr(mirroring, "send_file", fake_send_file)
    monkeypatch.setattr(mirroring, "send_message", fake_send_message)

    album = [
        make_message(emoji_caption, media=types.MessageMediaUnsupported(), channel_id=1000),
        make_message("y", media=types.MessageMediaUnsupported(), channel_id=1000),
    ]
    album[1].id = 2
    run(_proc(db).new_album(SOURCE, album, "link"))

    # Split path ran twice: primary attempt (rejected), retry with the
    # over-limit caption correctly stripped to "" (not left as-is).
    assert len(send_file_calls) == 2
    assert send_file_calls[1][0] == ""
    # The stripped caption was still delivered, as a separate tail text.
    assert emoji_caption in send_message_calls
    # And the album itself was tracked instead of being silently dropped.
    tracked = run(db.get_messages(1, SOURCE)) + run(db.get_messages(2, SOURCE))
    assert sorted(m.mirror_id for m in tracked) == [921, 922]
