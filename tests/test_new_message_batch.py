"""P8: new_message must persist all fan-out mappings in a single insert_batch."""

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
TARGETS = [-1002000000001, -1002000000002, -1002000000003]


def _cfg():
    return DirectionConfig(
        disable_delete=False, disable_edit=False, filters=EmptyMessageFilter()
    )


def test_single_insert_batch_for_fanout(monkeypatch):
    db = run(InMemoryDatabase())

    batches = []
    real_insert_batch = db.insert_batch

    async def spy_batch(entities):
        batches.append(list(entities))
        await real_insert_batch(entities)

    async def fail_insert(entity):  # must not be used
        raise AssertionError("new_message used per-row insert()")

    monkeypatch.setattr(db, "insert_batch", spy_batch)
    monkeypatch.setattr(db, "insert", fail_insert)

    async def fake_send_message(client, entity, message, **kw):
        return types.Message(id=555, peer_id=types.PeerChannel(1), message="x")

    monkeypatch.setattr(mirroring, "send_message", fake_send_message)

    proc = EventProcessor(
        chat_mapping={SOURCE: {t: [_cfg()] for t in TARGETS}},
        database=db,
        client=object(),
        logger=logging.getLogger("test"),
    )

    msg = make_message("hello", channel_id=1000)
    run(proc.new_message(SOURCE, msg, "https://t.me/c/1000/1"))

    assert len(batches) == 1
    assert {m.mirror_channel for m in batches[0]} == set(TARGETS)
    assert len(run(db.get_messages(msg.id, SOURCE))) == 3


def test_insert_batch_failure_is_logged_not_raised(monkeypatch, caplog):
    db = run(InMemoryDatabase())

    async def boom(entities):
        raise RuntimeError("db down")

    monkeypatch.setattr(db, "insert_batch", boom)

    async def fake_send_message(client, entity, message, **kw):
        return types.Message(id=555, peer_id=types.PeerChannel(1), message="x")

    monkeypatch.setattr(mirroring, "send_message", fake_send_message)

    logger = logging.getLogger("test.insert_batch")
    proc = EventProcessor(
        chat_mapping={SOURCE: {TARGETS[0]: [_cfg()]}},
        database=db,
        client=object(),
        logger=logger,
    )

    with caplog.at_level(logging.ERROR, logger="test.insert_batch"):
        run(proc.new_message(SOURCE, make_message("hi", channel_id=1000), "link"))

    assert any("sent but NOT tracked" in r.message for r in caplog.records)


@pytest.mark.parametrize(
    "exc", [errors.FloodWaitError, errors.FloodPremiumWaitError]
)
def test_flood_wait_propagates_out_of_handle_exceptions(monkeypatch, exc):
    """The __handle_exceptions decorator swallows everything except a >threshold
    FloodWait, which must reach past_mode's retry wrapper."""
    db = run(InMemoryDatabase())

    async def flooding_send(client, entity, message, **kw):
        raise exc(request=None)

    monkeypatch.setattr(mirroring, "send_message", flooding_send)

    proc = EventProcessor(
        chat_mapping={SOURCE: {TARGETS[0]: [_cfg()]}},
        database=db,
        client=object(),
        logger=logging.getLogger("test.flood"),
    )

    with pytest.raises(exc):
        run(proc.new_message(SOURCE, make_message("hi", channel_id=1000), "link"))
