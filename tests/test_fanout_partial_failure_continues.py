"""A bug in one target's filter chain (any exception other than
FloodWaitError/FloodPremiumWaitError/MediaDownloadError) must not abort
delivery to the fan-out's remaining targets. Before this fix, such an
exception unwound the whole per-target loop in new_message/new_album and
every target after the failing one was silently never attempted."""

import logging

from telethon.tl import types

import telemirror.mirroring as mirroring
from config import DirectionConfig
from telemirror.messagefilters import EmptyMessageFilter
from telemirror.mirroring import EventProcessor
from telemirror.storage import InMemoryDatabase
from tests.conftest import make_message, run

SOURCE = -1001000000000
TARGETS = [-1002000000001, -1002000000002, -1002000000003]


class _BoomFilter:
    restricted_content_allowed = False

    async def process(self, entity, event_type):
        raise RuntimeError("boom")


def _cfg(filters=None):
    return DirectionConfig(
        disable_delete=False, disable_edit=False, filters=filters or EmptyMessageFilter()
    )


def test_new_message_continues_past_one_targets_filter_bug(monkeypatch, caplog):
    db = run(InMemoryDatabase())
    sent_to = []

    async def fake_send_message(client, entity, message, **kw):
        sent_to.append(entity)
        return types.Message(id=555, peer_id=types.PeerChannel(1), message="x")

    monkeypatch.setattr(mirroring, "send_message", fake_send_message)

    configs = {
        TARGETS[0]: [_cfg()],
        TARGETS[1]: [_cfg(filters=_BoomFilter())],
        TARGETS[2]: [_cfg()],
    }
    proc = EventProcessor(
        chat_mapping={SOURCE: configs},
        database=db,
        client=object(),
        logger=logging.getLogger("test.fanoutbug"),
    )

    msg = make_message("hello", channel_id=1000)
    with caplog.at_level(logging.ERROR, logger="test.fanoutbug"):
        run(proc.new_message(SOURCE, msg, "https://t.me/c/1000/1"))

    assert set(sent_to) == {TARGETS[0], TARGETS[2]}
    assert any("filter chain failed" in r.message for r in caplog.records)


def test_new_album_continues_past_one_targets_filter_bug(monkeypatch, caplog):
    db = run(InMemoryDatabase())
    sent_to = []

    async def fake_send_file(client, entity, caption, file, **kw):
        sent_to.append(entity)
        return [types.Message(id=900, peer_id=types.PeerChannel(1), message="")]

    monkeypatch.setattr(mirroring, "send_file", fake_send_file)

    configs = {
        TARGETS[0]: [_cfg()],
        TARGETS[1]: [_cfg(filters=_BoomFilter())],
        TARGETS[2]: [_cfg()],
    }
    proc = EventProcessor(
        chat_mapping={SOURCE: configs},
        database=db,
        client=object(),
        logger=logging.getLogger("test.fanoutbug"),
    )

    album = [make_message("a", media=types.MessageMediaUnsupported(), channel_id=1000)]
    with caplog.at_level(logging.ERROR, logger="test.fanoutbug"):
        run(proc.new_album(SOURCE, album, "link"))

    assert set(sent_to) == {TARGETS[0], TARGETS[2]}
    assert any("filter chain failed" in r.message for r in caplog.records)
