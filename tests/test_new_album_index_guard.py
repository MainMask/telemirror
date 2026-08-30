"""Regression: new_album maps each sent message back to a source id by a
positional zip of `outgoing_messages` against `idxs`. If `send_file` returns a
different number of messages than there were source items, that mapping is
untrustworthy — the album must be left untracked (with a log line) rather than
written with wrong `original_id`s or crashing on `IndexError`."""

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
        logger=logging.getLogger("test.albumguard"),
    )


def _album():
    album = [
        make_message("a", media=types.MessageMediaUnsupported(), channel_id=1000),
        make_message("b", media=types.MessageMediaUnsupported(), channel_id=1000),
    ]
    album[1].id = 2
    return album


def test_count_mismatch_skips_tracking(monkeypatch, caplog):
    db = run(InMemoryDatabase())

    async def fake_send_file(client, entity, caption, file, **kw):
        # one more message than there were source items
        return [
            types.Message(id=900 + i, peer_id=types.PeerChannel(1), message="")
            for i in range(len(file) + 1)
        ]

    monkeypatch.setattr(mirroring, "send_file", fake_send_file)

    with caplog.at_level(logging.ERROR, logger="test.albumguard"):
        run(_proc(db).new_album(SOURCE, _album(), "link"))

    assert run(db.get_messages(1, SOURCE)) == []
    assert run(db.get_messages(2, SOURCE)) == []
    assert any("NOT tracked" in r.message for r in caplog.records)


def test_matching_count_tracks_with_correct_mapping(monkeypatch):
    db = run(InMemoryDatabase())

    async def fake_send_file(client, entity, caption, file, **kw):
        return [
            types.Message(id=901, peer_id=types.PeerChannel(1), message=""),
            types.Message(id=902, peer_id=types.PeerChannel(1), message=""),
        ]

    monkeypatch.setattr(mirroring, "send_file", fake_send_file)

    run(_proc(db).new_album(SOURCE, _album(), "link"))

    assert [m.mirror_id for m in run(db.get_messages(1, SOURCE))] == [901]
    assert [m.mirror_id for m in run(db.get_messages(2, SOURCE))] == [902]
