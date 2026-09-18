"""new_album shares new_message's tracking/flush contract (see
test_new_message_batch.py) via `EventProcessor._make_flush_inserted`:
sent rows are buffered and flushed per target, a failed flush is logged and
left queued for a later retry instead of raising, and a flood/MediaDownloadError
on a later target still flushes rows already earned by targets processed
before it. Before this, new_album wrote each target's rows directly inside
`track_media` with no buffering, no retry-on-failure and no flush before
re-raising -- a DB write failure for one target raised straight out of the
per-target loop and silently aborted every remaining target."""

import logging

import pytest
from telethon import errors
from telethon.tl import types

import telemirror.mirroring as mirroring
from config import DirectionConfig
from telemirror.messagefilters import EmptyMessageFilter, MediaDownloadError
from telemirror.mirroring import EventProcessor
from telemirror.storage import InMemoryDatabase
from tests.conftest import make_message, run

SOURCE = -1001000000000
TARGETS = [-1002000000001, -1002000000002]


def _cfg():
    return DirectionConfig(
        disable_delete=False, disable_edit=False, filters=EmptyMessageFilter()
    )


def _album():
    return [make_message("a", media=types.MessageMediaUnsupported(), channel_id=1000)]


def test_insert_batch_failure_does_not_abort_remaining_targets(monkeypatch, caplog):
    db = run(InMemoryDatabase())

    calls = {"n": 0}
    real_insert_batch = db.insert_batch

    async def flaky_insert_batch(entities):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("db down")
        await real_insert_batch(entities)

    monkeypatch.setattr(db, "insert_batch", flaky_insert_batch)

    async def fake_send_file(client, entity, caption, file, **kw):
        return [types.Message(id=900, peer_id=types.PeerChannel(1), message="")]

    monkeypatch.setattr(mirroring, "send_file", fake_send_file)

    proc = EventProcessor(
        chat_mapping={SOURCE: {t: [_cfg()] for t in TARGETS}},
        database=db,
        client=object(),
        logger=logging.getLogger("test.albumflush"),
    )

    with caplog.at_level(logging.ERROR, logger="test.albumflush"):
        run(proc.new_album(SOURCE, _album(), "link"))

    assert any("sent but NOT tracked" in r.message for r in caplog.records)
    # TARGETS[1]'s own flush retried and persisted TARGETS[0]'s still-queued
    # row alongside its own, instead of TARGETS[0]'s failure aborting the fan-out.
    tracked = run(db.get_messages(1, SOURCE))
    assert {m.mirror_channel for m in tracked} == set(TARGETS)


class _MDEFilter:
    restricted_content_allowed = False

    async def process(self, album, event_type):
        raise MediaDownloadError("t.me/c/1/2: exhausted")


def test_media_download_error_mid_fanout_persists_already_sent_targets(monkeypatch):
    """Same contract as new_message: a filter raising MediaDownloadError on a
    later target must still flush the rows for targets already delivered."""
    db = run(InMemoryDatabase())

    async def fake_send_file(client, entity, caption, file, **kw):
        return [types.Message(id=900, peer_id=types.PeerChannel(1), message="")]

    monkeypatch.setattr(mirroring, "send_file", fake_send_file)

    proc = EventProcessor(
        chat_mapping={
            SOURCE: {
                TARGETS[0]: [_cfg()],
                TARGETS[1]: [DirectionConfig(
                    disable_delete=False, disable_edit=False, filters=_MDEFilter()
                )],
            }
        },
        database=db,
        client=object(),
        logger=logging.getLogger("test.albummde"),
        strict_media_errors=True,
    )

    with pytest.raises(MediaDownloadError):
        run(proc.new_album(SOURCE, _album(), "link"))

    tracked = run(db.get_messages(1, SOURCE))
    assert {m.mirror_channel for m in tracked} == {TARGETS[0]}


@pytest.mark.parametrize("exc", [errors.FloodWaitError, errors.FloodPremiumWaitError])
def test_flood_mid_fanout_persists_already_sent_targets(monkeypatch, exc):
    """Same contract as new_message: a flood on a later fan-out target must
    still flush the rows for targets already delivered before the exception
    unwinds."""
    db = run(InMemoryDatabase())

    async def fake_send_file(client, entity, caption, file, **kw):
        if entity == TARGETS[1]:
            raise exc(request=None)
        return [types.Message(id=900, peer_id=types.PeerChannel(1), message="")]

    monkeypatch.setattr(mirroring, "send_file", fake_send_file)

    proc = EventProcessor(
        chat_mapping={SOURCE: {t: [_cfg()] for t in TARGETS}},
        database=db,
        client=object(),
        logger=logging.getLogger("test.albumflood"),
    )

    with pytest.raises(exc):
        run(proc.new_album(SOURCE, _album(), "link"))

    tracked = run(db.get_messages(1, SOURCE))
    assert {m.mirror_channel for m in tracked} == {TARGETS[0]}
