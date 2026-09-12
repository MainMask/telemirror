"""FileReferenceExpiredError handling: a stale file_reference on send triggers
one refetch-and-retry. Two things must hold for `new_album`'s refresh branch
specifically: a `get_messages` result whose length doesn't match `idxs` must
be treated the same as any other untrustworthy refetch (logged, left
untracked, no crash/misalignment) — the same discipline the non-refresh path
already applies via its own `len(outgoing_messages) != len(idxs)` guard —
and a clean refresh must still track the album/message correctly. A third
thing must hold for both `new_message` and `new_album`: if the *retried* send
itself hits a FloodWaitError, that must propagate to past_mode's retry
wrapper like every other send attempt in this module — not get swallowed by
the refresh branch's generic `except Exception`."""

import logging

import pytest
from telethon import errors
from telethon.tl import types

import telemirror.mirroring as mirroring
from config import DirectionConfig
from telemirror.messagefilters import EmptyMessageFilter
from telemirror.mirroring import EventProcessor
from telemirror.storage import InMemoryDatabase
from tests.conftest import make_message, run

SOURCE = -1001000000000
TARGET = -1002000000001
TARGET2 = -1002000000002


class _Stale:
    """Distinguishable media marker; deepcopy preserves the type, not identity."""


class _Fresh:
    """Distinguishable media marker; deepcopy preserves the type, not identity."""


def _cfg():
    return DirectionConfig(
        disable_delete=False, disable_edit=False, filters=EmptyMessageFilter()
    )


class _FakeClient:
    def __init__(self, get_messages_result):
        self._get_messages_result = get_messages_result
        self.get_messages_calls = 0

    async def get_messages(self, chat_id, ids):
        self.get_messages_calls += 1
        return self._get_messages_result


def _proc(db, get_messages_result):
    return EventProcessor(
        chat_mapping={SOURCE: {TARGET: [_cfg()]}},
        database=db,
        client=_FakeClient(get_messages_result),
        logger=logging.getLogger("test.filereference"),
    )


def _album():
    album = [
        make_message("a", media=types.MessageMediaUnsupported(), channel_id=1000),
        make_message("b", media=types.MessageMediaUnsupported(), channel_id=1000),
    ]
    album[1].id = 2
    return album


def test_new_album_refresh_length_mismatch_skips_tracking(monkeypatch, caplog):
    db = run(InMemoryDatabase())

    calls = []

    async def fake_send_file(client, entity, caption, file, **kw):
        calls.append(file)
        raise errors.FileReferenceExpiredError(request=None)

    monkeypatch.setattr(mirroring, "send_file", fake_send_file)

    # get_messages comes back with only one item for a two-item album.
    fresh_short = [
        types.Message(
            id=1, peer_id=types.PeerChannel(1000),
            media=types.MessageMediaUnsupported(),
        )
    ]

    with caplog.at_level(logging.ERROR, logger="test.filereference"):
        run(_proc(db, fresh_short).new_album(SOURCE, _album(), "link"))

    assert len(calls) == 1
    assert run(db.get_messages(1, SOURCE)) == []
    assert run(db.get_messages(2, SOURCE)) == []
    assert any(
        "can't refresh file_reference" in r.message for r in caplog.records
    )


def test_new_album_refresh_success_tracks_with_correct_mapping(monkeypatch):
    db = run(InMemoryDatabase())

    calls = []

    async def fake_send_file(client, entity, caption, file, **kw):
        calls.append(file)
        if len(calls) == 1:
            raise errors.FileReferenceExpiredError(request=None)
        return [
            types.Message(id=901, peer_id=types.PeerChannel(1), message=""),
            types.Message(id=902, peer_id=types.PeerChannel(1), message=""),
        ]

    monkeypatch.setattr(mirroring, "send_file", fake_send_file)

    fresh_full = [
        types.Message(
            id=1, peer_id=types.PeerChannel(1000),
            media=types.MessageMediaUnsupported(),
        ),
        types.Message(
            id=2, peer_id=types.PeerChannel(1000),
            media=types.MessageMediaUnsupported(),
        ),
    ]

    run(_proc(db, fresh_full).new_album(SOURCE, _album(), "link"))

    assert len(calls) == 2
    assert [m.mirror_id for m in run(db.get_messages(1, SOURCE))] == [901]
    assert [m.mirror_id for m in run(db.get_messages(2, SOURCE))] == [902]


def test_new_message_refresh_success_tracks_message(monkeypatch):
    db = run(InMemoryDatabase())

    calls = []

    async def fake_send_message(client, entity, message, **kw):
        calls.append(message)
        if len(calls) == 1:
            raise errors.FileReferenceExpiredError(request=None)
        return types.Message(id=777, peer_id=types.PeerChannel(1), message="")

    monkeypatch.setattr(mirroring, "send_message", fake_send_message)

    fresh_msg = types.Message(
        id=1, peer_id=types.PeerChannel(1000),
        media=types.MessageMediaUnsupported(),
    )

    msg = make_message("hi", media=types.MessageMediaUnsupported(), channel_id=1000)

    run(_proc(db, fresh_msg).new_message(SOURCE, msg, "link"))

    assert len(calls) == 2
    assert [m.mirror_id for m in run(db.get_messages(1, SOURCE))] == [777]


def test_new_message_refresh_retry_does_not_swallow_floodwait(monkeypatch):
    db = run(InMemoryDatabase())

    calls = []

    async def fake_send_message(client, entity, message, **kw):
        calls.append(message)
        if len(calls) == 1:
            raise errors.FileReferenceExpiredError(request=None)
        raise errors.FloodWaitError(request=None, capture=5)

    monkeypatch.setattr(mirroring, "send_message", fake_send_message)

    fresh_msg = types.Message(
        id=1, peer_id=types.PeerChannel(1000),
        media=types.MessageMediaUnsupported(),
    )

    msg = make_message("hi", media=types.MessageMediaUnsupported(), channel_id=1000)

    with pytest.raises(errors.FloodWaitError):
        run(_proc(db, fresh_msg).new_message(SOURCE, msg, "link"))

    assert len(calls) == 2


def test_new_album_refresh_retry_does_not_swallow_floodwait(monkeypatch):
    db = run(InMemoryDatabase())

    calls = []

    async def fake_send_file(client, entity, caption, file, **kw):
        calls.append(file)
        if len(calls) == 1:
            raise errors.FileReferenceExpiredError(request=None)
        raise errors.FloodWaitError(request=None, capture=5)

    monkeypatch.setattr(mirroring, "send_file", fake_send_file)

    fresh_full = [
        types.Message(
            id=1, peer_id=types.PeerChannel(1000),
            media=types.MessageMediaUnsupported(),
        ),
        types.Message(
            id=2, peer_id=types.PeerChannel(1000),
            media=types.MessageMediaUnsupported(),
        ),
    ]

    with pytest.raises(errors.FloodWaitError):
        run(_proc(db, fresh_full).new_album(SOURCE, _album(), "link"))

    assert len(calls) == 2


def test_new_message_refresh_refetch_generic_error_skips_target_only(monkeypatch):
    """A non-Flood exception from the refetch (e.g. a dropped connection) must
    be logged and skipped for just this outgoing chat — not escape the whole
    fan-out and cost every other target the message."""
    db = run(InMemoryDatabase())

    send_calls = []

    async def fake_send_message(client, entity, message, **kw):
        send_calls.append(entity)
        raise errors.FileReferenceExpiredError(request=None)

    monkeypatch.setattr(mirroring, "send_message", fake_send_message)

    class _FlakyClient:
        def __init__(self):
            self.get_messages_calls = 0

        async def get_messages(self, chat_id, ids):
            self.get_messages_calls += 1
            raise ConnectionError("dc down")

    client = _FlakyClient()
    proc = EventProcessor(
        chat_mapping={SOURCE: {TARGET: [_cfg()], TARGET2: [_cfg()]}},
        database=db,
        client=client,
        logger=logging.getLogger("test.filereference"),
    )

    msg = make_message("hi", media=types.MessageMediaUnsupported(), channel_id=1000)

    run(proc.new_message(SOURCE, msg, "link"))

    # Both targets attempted the send, hit the stale reference, and the
    # refetch failed for both — neither is tracked, but neither raised.
    assert len(send_calls) == 2
    assert client.get_messages_calls == 2
    assert run(db.get_messages(1, SOURCE)) == []


def test_new_album_refresh_refetch_generic_error_skips_target_only(monkeypatch):
    """Same as the message-level test above, but for new_album's refetch."""
    db = run(InMemoryDatabase())

    send_calls = []

    async def fake_send_file(client, entity, caption, file, **kw):
        send_calls.append(entity)
        raise errors.FileReferenceExpiredError(request=None)

    monkeypatch.setattr(mirroring, "send_file", fake_send_file)

    class _FlakyClient:
        def __init__(self):
            self.get_messages_calls = 0

        async def get_messages(self, chat_id, ids):
            self.get_messages_calls += 1
            raise ConnectionError("dc down")

    client = _FlakyClient()
    proc = EventProcessor(
        chat_mapping={SOURCE: {TARGET: [_cfg()], TARGET2: [_cfg()]}},
        database=db,
        client=client,
        logger=logging.getLogger("test.filereference"),
    )

    run(proc.new_album(SOURCE, _album(), "link"))

    assert len(send_calls) == 2
    assert client.get_messages_calls == 2
    assert run(db.get_messages(1, SOURCE)) == []
    assert run(db.get_messages(2, SOURCE)) == []


def test_new_message_refresh_is_reused_across_fanout_targets(monkeypatch):
    """A stale file_reference is a property of the *source* message, shared by
    every fan-out target. Once refreshed for the first target, later targets
    must reuse it instead of independently refetching the same reference."""
    db = run(InMemoryDatabase())

    calls = []

    async def fake_send_message(client, entity, message, **kw):
        calls.append(entity)
        if isinstance(message.media, _Stale):
            raise errors.FileReferenceExpiredError(request=None)
        return types.Message(
            id=700 + len(calls), peer_id=types.PeerChannel(1), message=""
        )

    monkeypatch.setattr(mirroring, "send_message", fake_send_message)

    fresh_msg = types.Message(id=1, peer_id=types.PeerChannel(1000), media=_Fresh())
    client = _FakeClient(fresh_msg)
    proc = EventProcessor(
        chat_mapping={SOURCE: {TARGET: [_cfg()], TARGET2: [_cfg()]}},
        database=db,
        client=client,
        logger=logging.getLogger("test.filereference"),
    )

    msg = make_message("hi", media=_Stale(), channel_id=1000)

    run(proc.new_message(SOURCE, msg, "link"))

    # target 1: fails once (stale), refreshes, succeeds — target 2: succeeds
    # on the first try because `message` itself was updated after the refresh.
    assert len(calls) == 3
    assert client.get_messages_calls == 1
    assert len(run(db.get_messages(1, SOURCE))) == 2


def test_new_message_refresh_retry_caption_too_long_splits(monkeypatch):
    """A message with both a stale file_reference AND a >1024-char caption
    must still be delivered: after the refresh, a MediaCaptionTooLongError on
    the retry send must fall into the same split-media-then-text-tail
    fallback the primary attempt uses, not be dropped as a generic error."""
    db = run(InMemoryDatabase())

    calls = []

    async def fake_send_message(client, entity, message, **kw):
        calls.append(message)
        if len(calls) == 1:
            raise errors.FileReferenceExpiredError(request=None)
        if len(calls) == 2:
            raise errors.MediaCaptionTooLongError(request=None)
        if len(calls) == 3:
            return types.Message(id=777, peer_id=types.PeerChannel(1), message="")
        return types.Message(id=778, peer_id=types.PeerChannel(1), message="")

    monkeypatch.setattr(mirroring, "send_message", fake_send_message)

    fresh_msg = types.Message(
        id=1, peer_id=types.PeerChannel(1000),
        media=types.MessageMediaUnsupported(),
    )

    long_caption = "x" * 1025
    msg = make_message(long_caption, media=types.MessageMediaUnsupported(), channel_id=1000)

    run(_proc(db, fresh_msg).new_message(SOURCE, msg, "link"))

    assert len(calls) == 4
    # 3rd call: media resent with caption stripped
    assert calls[2].message == ""
    # 4th call: the text tail carries the original long caption
    assert calls[3] == long_caption
    # only the media message is tracked, the text tail is not
    assert [m.mirror_id for m in run(db.get_messages(1, SOURCE))] == [777]


def test_new_album_refresh_retry_caption_too_long_splits(monkeypatch):
    """Same as the message-level test above, but for an album: a stale
    file_reference plus an over-long caption on one of its items must still
    result in a delivered, caption-split album."""
    db = run(InMemoryDatabase())

    file_calls = []
    text_calls = []

    async def fake_send_file(client, entity, caption, file, **kw):
        file_calls.append(caption)
        if len(file_calls) == 1:
            raise errors.FileReferenceExpiredError(request=None)
        if len(file_calls) == 2:
            raise errors.MediaCaptionTooLongError(request=None)
        return [
            types.Message(id=900 + i, peer_id=types.PeerChannel(1), message="")
            for i in range(len(file))
        ]

    async def fake_send_message(client, entity, message, **kw):
        text_calls.append(message)
        return types.Message(id=950, peer_id=types.PeerChannel(1), message="")

    monkeypatch.setattr(mirroring, "send_file", fake_send_file)
    monkeypatch.setattr(mirroring, "send_message", fake_send_message)

    fresh_full = [
        types.Message(
            id=1, peer_id=types.PeerChannel(1000),
            media=types.MessageMediaUnsupported(),
        ),
        types.Message(
            id=2, peer_id=types.PeerChannel(1000),
            media=types.MessageMediaUnsupported(),
        ),
    ]

    long_caption = "y" * 1025
    album = [
        make_message(long_caption, media=types.MessageMediaUnsupported(), channel_id=1000),
        make_message("short", media=types.MessageMediaUnsupported(), channel_id=1000),
    ]
    album[1].id = 2

    run(_proc(db, fresh_full).new_album(SOURCE, album, "link"))

    assert len(file_calls) == 3
    # final send_file call: the long caption was stripped, the short one kept
    assert file_calls[2] == ["", "short"]
    # the stripped caption was sent as a separate text tail
    assert text_calls == [long_caption]
    assert [m.mirror_id for m in run(db.get_messages(1, SOURCE))] == [900]
    assert [m.mirror_id for m in run(db.get_messages(2, SOURCE))] == [901]


def test_new_message_caption_too_long_then_stale_reference_splits_after_refresh(monkeypatch):
    """Reverse ordering of the test above: MediaCaptionTooLongError on the
    *primary* attempt, then the caption-split fallback's own media-only send
    hits FileReferenceExpiredError (the reference was already stale too).
    Must still refresh and retry, not be dropped by the fallback's generic
    exception handler."""
    db = run(InMemoryDatabase())

    calls = []

    async def fake_send_message(client, entity, message, **kw):
        calls.append(message)
        if len(calls) == 1:
            raise errors.MediaCaptionTooLongError(request=None)
        if len(calls) == 2:
            raise errors.FileReferenceExpiredError(request=None)
        if len(calls) == 3:
            return types.Message(id=777, peer_id=types.PeerChannel(1), message="")
        return types.Message(id=778, peer_id=types.PeerChannel(1), message="")

    monkeypatch.setattr(mirroring, "send_message", fake_send_message)

    fresh_msg = types.Message(
        id=1, peer_id=types.PeerChannel(1000),
        media=types.MessageMediaUnsupported(),
    )

    long_caption = "x" * 1025
    msg = make_message(long_caption, media=types.MessageMediaUnsupported(), channel_id=1000)

    run(_proc(db, fresh_msg).new_message(SOURCE, msg, "link"))

    assert len(calls) == 4
    # 3rd call: media resent with the refreshed reference, caption stripped
    assert calls[2].message == ""
    # 4th call: the text tail carries the original long caption
    assert calls[3] == long_caption
    # only the media message is tracked, the text tail is not
    assert [m.mirror_id for m in run(db.get_messages(1, SOURCE))] == [777]


def test_new_album_caption_too_long_then_stale_reference_splits_after_refresh(monkeypatch):
    """Reverse ordering of the test above: MediaCaptionTooLongError on the
    *primary* attempt, then the caption-split fallback's own send_file hits
    FileReferenceExpiredError (the reference was already stale too). Must
    still refresh and retry, not be dropped by the fallback's generic
    exception handler."""
    db = run(InMemoryDatabase())

    file_calls = []
    text_calls = []

    async def fake_send_file(client, entity, caption, file, **kw):
        file_calls.append(caption)
        if len(file_calls) == 1:
            raise errors.MediaCaptionTooLongError(request=None)
        if len(file_calls) == 2:
            raise errors.FileReferenceExpiredError(request=None)
        return [
            types.Message(id=900 + i, peer_id=types.PeerChannel(1), message="")
            for i in range(len(file))
        ]

    async def fake_send_message(client, entity, message, **kw):
        text_calls.append(message)
        return types.Message(id=950, peer_id=types.PeerChannel(1), message="")

    monkeypatch.setattr(mirroring, "send_file", fake_send_file)
    monkeypatch.setattr(mirroring, "send_message", fake_send_message)

    fresh_full = [
        types.Message(
            id=1, peer_id=types.PeerChannel(1000),
            media=types.MessageMediaUnsupported(),
        ),
        types.Message(
            id=2, peer_id=types.PeerChannel(1000),
            media=types.MessageMediaUnsupported(),
        ),
    ]

    long_caption = "y" * 1025
    album = [
        make_message(long_caption, media=types.MessageMediaUnsupported(), channel_id=1000),
        make_message("short", media=types.MessageMediaUnsupported(), channel_id=1000),
    ]
    album[1].id = 2

    run(_proc(db, fresh_full).new_album(SOURCE, album, "link"))

    assert len(file_calls) == 3
    # final send_file call: refreshed reference, long caption stripped
    assert file_calls[2] == ["", "short"]
    assert text_calls == [long_caption]
    assert [m.mirror_id for m in run(db.get_messages(1, SOURCE))] == [900]
    assert [m.mirror_id for m in run(db.get_messages(2, SOURCE))] == [901]


def test_new_album_refresh_is_reused_across_fanout_targets(monkeypatch):
    db = run(InMemoryDatabase())

    calls = []

    async def fake_send_file(client, entity, caption, file, **kw):
        calls.append(entity)
        if any(isinstance(f, _Stale) for f in file):
            raise errors.FileReferenceExpiredError(request=None)
        return [
            types.Message(id=900 + len(calls) * 10 + i, peer_id=types.PeerChannel(1), message="")
            for i in range(len(file))
        ]

    monkeypatch.setattr(mirroring, "send_file", fake_send_file)

    fresh_list = [
        types.Message(id=1, peer_id=types.PeerChannel(1000), media=_Fresh()),
        types.Message(id=2, peer_id=types.PeerChannel(1000), media=_Fresh()),
    ]
    client = _FakeClient(fresh_list)
    proc = EventProcessor(
        chat_mapping={SOURCE: {TARGET: [_cfg()], TARGET2: [_cfg()]}},
        database=db,
        client=client,
        logger=logging.getLogger("test.filereference"),
    )

    album = [
        make_message("a", media=_Stale(), channel_id=1000),
        make_message("b", media=_Stale(), channel_id=1000),
    ]
    album[1].id = 2

    run(proc.new_album(SOURCE, album, "link"))

    assert len(calls) == 3
    assert client.get_messages_calls == 1
    assert len(run(db.get_messages(1, SOURCE))) == 2
    assert len(run(db.get_messages(2, SOURCE))) == 2
