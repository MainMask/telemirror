"""Smoke coverage for past_mode.py: checkpoint integrity + the replay loop
(grouping, checkpoint advance, buffer vs streaming)."""

import logging

import pytest
from telethon import errors
from telethon.tl import types

import past_mode
from config import DirectionConfig, PastModeConfig
from telemirror.messagefilters import EmptyMessageFilter
from telemirror.storage import InMemoryDatabase, MirrorMessage
from tests.conftest import run

SRC = -1001111111111
TGT = -1002222222222
_LOG = logging.getLogger("test.past_mode")


def _cfg(pm: PastModeConfig) -> DirectionConfig:
    return DirectionConfig(
        disable_delete=False,
        disable_edit=False,
        filters=EmptyMessageFilter(),
        past_mode=pm,
    )


# --- _integrity_check -------------------------------------------------------

def test_integrity_no_checkpoint():
    db = run(InMemoryDatabase())
    assert run(past_mode._integrity_check(db, SRC, TGT, _LOG)) == (None, 0)


def test_integrity_checkpoint_without_mirrors():
    db = run(InMemoryDatabase())
    run(db.set_past_mode_checkpoint(SRC, TGT, 50))
    assert run(past_mode._integrity_check(db, SRC, TGT, _LOG)) == (50, 0)


def test_integrity_rolls_back_stale_checkpoint():
    db = run(InMemoryDatabase())
    run(db.set_past_mode_checkpoint(SRC, TGT, 10))
    run(db.insert_batch([MirrorMessage(oid, SRC, oid + 900, TGT) for oid in (5, 42)]))
    # checkpoint 10 < max mirrored 42 -> rolled forward to 42
    assert run(past_mode._integrity_check(db, SRC, TGT, _LOG)) == (42, 2)
    assert run(db.get_past_mode_checkpoint(SRC, TGT)) == 42


def test_integrity_keeps_healthy_checkpoint():
    db = run(InMemoryDatabase())
    run(db.set_past_mode_checkpoint(SRC, TGT, 99))
    run(db.insert_batch([MirrorMessage(42, SRC, 942, TGT)]))
    assert run(past_mode._integrity_check(db, SRC, TGT, _LOG)) == (99, 1)


# --- _replay_direction ----------------------------------------------------

def _msg(mid, grouped_id=None):
    return types.Message(
        id=mid, peer_id=types.PeerChannel(1), message=f"m{mid}", grouped_id=grouped_id
    )


class _Total:
    def __init__(self, n):
        self.total = n


class FakeClient:
    def __init__(self, messages):
        self._messages = sorted(messages, key=lambda m: m.id)

    async def get_messages(self, entity, limit=None, **kw):
        return _Total(len(self._messages))

    def iter_messages(self, entity, limit=None, reverse=False, min_id=None, **kw):
        msgs = list(self._messages)
        if min_id is not None:
            msgs = [m for m in msgs if m.id > min_id]
        if not reverse:
            msgs = list(reversed(msgs))  # newest first
        if limit is not None:
            msgs = msgs[:limit]

        async def gen():
            for m in msgs:
                yield m

        return gen()


def _run_replay(monkeypatch, messages, pm, db=None):
    calls = []

    class Rec:
        def __init__(self, **kw):
            pass

        async def new_message(self, chat, msg, link):
            calls.append(("new", msg.id))

        async def new_album(self, chat, album, link):
            calls.append(("album", tuple(m.id for m in album)))

    monkeypatch.setattr(past_mode, "EventProcessor", Rec)
    db = db or run(InMemoryDatabase())
    run(
        past_mode._replay_direction(
            FakeClient(messages), db, SRC, TGT, _cfg(pm), _LOG
        )
    )
    return calls, db


def test_replay_full_history_groups_and_checkpoints(monkeypatch):
    msgs = [_msg(1), _msg(2, grouped_id=7), _msg(3, grouped_id=7), _msg(4)]
    calls, db = _run_replay(monkeypatch, msgs, PastModeConfig(full_history=True, send_delay=0))
    assert calls == [("new", 1), ("album", (2, 3)), ("new", 4)]
    assert run(db.get_past_mode_checkpoint(SRC, TGT)) == 4


def test_replay_last_n_buffer_oldest_first(monkeypatch):
    msgs = [_msg(i) for i in range(1, 11)]
    calls, db = _run_replay(monkeypatch, msgs, PastModeConfig(last_n=3, send_delay=0))
    assert calls == [("new", 8), ("new", 9), ("new", 10)]
    assert run(db.get_past_mode_checkpoint(SRC, TGT)) == 10


@pytest.mark.parametrize(
    "exc", [errors.FloodWaitError, errors.FloodPremiumWaitError]
)
def test_replay_floodwait_does_not_advance_checkpoint(monkeypatch, exc):
    """A FloodWait raised while sending must propagate (not be swallowed) so the
    checkpoint stays put and the un-sent message is retried."""
    calls = []

    class Rec:
        def __init__(self, **kw):
            pass

        async def new_message(self, chat, msg, link):
            calls.append(msg.id)
            if msg.id == 2:
                raise exc(request=None)

    monkeypatch.setattr(past_mode, "EventProcessor", Rec)
    db = run(InMemoryDatabase())
    with pytest.raises(exc):
        run(
            past_mode._replay_direction(
                FakeClient([_msg(1), _msg(2), _msg(3)]), db, SRC, TGT,
                _cfg(PastModeConfig(full_history=True, send_delay=0)), _LOG,
            )
        )
    assert calls == [1, 2]
    assert run(db.get_past_mode_checkpoint(SRC, TGT)) == 1


@pytest.mark.parametrize(
    "exc", [errors.FloodWaitError, errors.FloodPremiumWaitError]
)
def test_replay_with_retry_waits_out_flood(monkeypatch, exc):
    """_replay_with_retry sleeps and retries on either flood type (past_mode's
    retry loop must cover FloodPremiumWaitError, not just FloodWaitError)."""
    attempts = []
    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(past_mode.asyncio, "sleep", fake_sleep)

    async def fake_replay(client, database, source_id, target_id, cfg, logger):
        attempts.append(1)
        if len(attempts) == 1:
            raise exc(request=None)

    monkeypatch.setattr(past_mode, "_replay_direction", fake_replay)

    run(
        past_mode._replay_with_retry(
            object(), run(InMemoryDatabase()), SRC, TGT,
            _cfg(PastModeConfig(full_history=True, send_delay=0)), _LOG,
        )
    )
    assert len(attempts) == 2
    assert len(slept) == 1


def test_replay_resumes_from_checkpoint(monkeypatch):
    db = run(InMemoryDatabase())
    run(db.set_past_mode_checkpoint(SRC, TGT, 2))
    run(db.insert_batch([MirrorMessage(2, SRC, 902, TGT)]))
    msgs = [_msg(i) for i in range(1, 6)]
    calls, db = _run_replay(
        monkeypatch, msgs, PastModeConfig(full_history=True, send_delay=0), db=db
    )
    assert calls == [("new", 3), ("new", 4), ("new", 5)]  # min_id=2 is exclusive


# --- _edit_links_pass ----------------------------------------------------

class _EditFakeClient:
    def __init__(self, src_messages):
        self._src = {m.id: m for m in src_messages}
        self.edits = []

    async def get_messages(self, entity, ids=None, limit=None, **kw):
        if ids is not None:
            return [self._src.get(i) for i in ids]
        return _Total(len(self._src))

    async def edit_message(self, entity, message, text, formatting_entities=None, **kw):
        self.edits.append((entity, message, text, formatting_entities))


def test_edit_links_pass_rewrites_cross_message_link(monkeypatch):
    from telemirror.misc.links import private_message_link

    db = run(InMemoryDatabase())
    # message 10 (mirrored to 910) links to message 7 of the same channel
    # (mirrored to 907) — the edit pass must repoint the link at 907.
    run(db.insert_batch([
        MirrorMessage(10, SRC, 910, TGT),
        MirrorMessage(7, SRC, 907, TGT),
    ]))

    src_peer = -SRC - 1000000000000  # PeerChannel raw id for a t.me/c/ link
    linked = types.Message(
        id=10,
        peer_id=types.PeerChannel(1),
        message="link",
        entities=[types.MessageEntityTextUrl(
            offset=0, length=4, url=f"https://t.me/c/{src_peer}/7"
        )],
    )
    client = _EditFakeClient([linked])

    run(past_mode._edit_links_pass(
        client, db, [(SRC, TGT, _cfg(PastModeConfig(full_history=True, send_delay=0)))],
        _LOG,
    ))

    assert len(client.edits) == 1
    entity, message_id, _text, ents = client.edits[0]
    assert (entity, message_id) == (TGT, 910)
    assert ents[0].url == private_message_link(TGT, 907)
