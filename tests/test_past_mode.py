"""Smoke coverage for past_mode.py: checkpoint integrity + the replay loop
(grouping, checkpoint advance, buffer vs streaming)."""

import logging

import pytest
from telethon import errors
from telethon.tl import types

import past_mode
from config import DirectionConfig, PastModeConfig
from telemirror.messagefilters import EmptyMessageFilter, MediaDownloadError
from telemirror.storage import InMemoryDatabase, MirrorMessage
from tests.conftest import run

SRC = -1001111111111
TGT = -1002222222222
_LOG = logging.getLogger("test.past_mode")


def _cfg(pm: PastModeConfig, from_topic_id=None) -> DirectionConfig:
    return DirectionConfig(
        disable_delete=False,
        disable_edit=False,
        filters=EmptyMessageFilter(),
        from_topic_id=from_topic_id,
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
            FakeClient(messages), db, SRC, TGT, [_cfg(pm)], _LOG
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
                [_cfg(PastModeConfig(full_history=True, send_delay=0))], _LOG,
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

    async def fake_replay(client, database, source_id, target_id, cfgs, logger, total=None):
        attempts.append(1)
        if len(attempts) == 1:
            raise exc(request=None)
        return 0

    monkeypatch.setattr(past_mode, "_replay_direction", fake_replay)

    run(
        past_mode._replay_with_retry(
            object(), run(InMemoryDatabase()), SRC, TGT,
            [_cfg(PastModeConfig(full_history=True, send_delay=0))], _LOG,
        )
    )
    assert len(attempts) == 2
    assert len(slept) == 1


@pytest.mark.parametrize(
    "exc", [errors.FloodWaitError, errors.FloodPremiumWaitError]
)
def test_replay_with_retry_gives_up_after_flood_retry_limit_at_same_checkpoint(
    monkeypatch, exc
):
    """A FloodWait that keeps recurring at the same checkpoint (Telegram never
    clears the throttle) must eventually raise instead of retrying forever —
    an unbounded retry would leave the process alive but stuck, invisible to
    systemd's Restart= (pass 13)."""
    attempts = []

    async def fake_sleep(seconds):
        pass

    monkeypatch.setattr(past_mode.asyncio, "sleep", fake_sleep)

    async def always_flooding(client, database, source_id, target_id, cfgs, logger, total=None):
        attempts.append(1)
        raise exc(request=None)

    monkeypatch.setattr(past_mode, "_replay_direction", always_flooding)

    with pytest.raises(exc):
        run(
            past_mode._replay_with_retry(
                object(), run(InMemoryDatabase()), SRC, TGT,
                [_cfg(PastModeConfig(full_history=True, send_delay=0))], _LOG,
            )
        )
    assert len(attempts) == past_mode._FLOOD_RETRY_LIMIT + 1


def test_replay_with_retry_flood_retry_counter_resets_on_checkpoint_progress(monkeypatch):
    """Real progress between flood waits (the checkpoint keeps moving) resets
    the give-up counter — normal flood-limiting churn across many directions
    in a long backfill must not trip the limit early."""
    attempts = []
    db = run(InMemoryDatabase())

    async def fake_sleep(seconds):
        pass

    monkeypatch.setattr(past_mode.asyncio, "sleep", fake_sleep)

    async def flooding_with_progress(client, database, source_id, target_id, cfgs, logger, total=None):
        attempts.append(1)
        if len(attempts) > past_mode._FLOOD_RETRY_LIMIT + 5:
            return 0  # eventually succeeds
        await database.set_past_mode_checkpoint(source_id, target_id, len(attempts))
        raise errors.FloodWaitError(request=None)

    monkeypatch.setattr(past_mode, "_replay_direction", flooding_with_progress)

    run(
        past_mode._replay_with_retry(
            object(), db, SRC, TGT,
            [_cfg(PastModeConfig(full_history=True, send_delay=0))], _LOG,
        )
    )
    # Exceeds _FLOOD_RETRY_LIMIT total retries but never at a stuck checkpoint,
    # so it keeps going instead of giving up early.
    assert len(attempts) == past_mode._FLOOD_RETRY_LIMIT + 6


def test_replay_with_retry_waits_out_media_download_error(monkeypatch):
    """A MediaDownloadError (transient download outlived its retries) is waited
    out and the direction re-run from the checkpoint, like a FloodWait."""
    attempts = []
    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(past_mode.asyncio, "sleep", fake_sleep)

    async def fake_replay(client, database, source_id, target_id, cfgs, logger, total=None):
        attempts.append(1)
        if len(attempts) == 1:
            raise MediaDownloadError("t.me/c/1/2: exhausted")
        return 0

    monkeypatch.setattr(past_mode, "_replay_direction", fake_replay)

    run(
        past_mode._replay_with_retry(
            object(), run(InMemoryDatabase()), SRC, TGT,
            [_cfg(PastModeConfig(full_history=True, send_delay=0))], _LOG,
        )
    )
    assert len(attempts) == 2
    assert slept == [past_mode._MEDIA_RETRY_WAIT]


def test_replay_with_retry_skips_stuck_message_after_limit(monkeypatch):
    """A message that keeps failing to download past the limit is skipped:
    checkpoint jumps past it, an alert is sent, the replay continues (no crash
    loop, live mirror not held down for hours)."""
    attempts = []
    notified = []

    async def fake_sleep(seconds):
        pass

    async def fake_notify(client, src, mid, log):
        notified.append(mid)

    monkeypatch.setattr(past_mode.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(past_mode, "_notify_skipped", fake_notify)

    db = run(InMemoryDatabase())

    async def stuck_then_done(client, database, source_id, target_id, cfgs, logger, total=None):
        attempts.append(1)
        if len(attempts) <= past_mode._MEDIA_RETRY_LIMIT + 1:
            raise MediaDownloadError("t.me/c/1/77: exhausted", message_id=77)
        return 0

    monkeypatch.setattr(past_mode, "_replay_direction", stuck_then_done)

    run(
        past_mode._replay_with_retry(
            object(), db, SRC, TGT,
            [_cfg(PastModeConfig(full_history=True, send_delay=0))], _LOG,
        )
    )
    assert notified == [77]
    assert run(db.get_past_mode_checkpoint(SRC, TGT)) == 77


def test_replay_with_retry_reraises_when_stuck_message_unknown(monkeypatch):
    """No message_id on the error → can't skip → propagate (process exits)."""
    async def fake_sleep(seconds):
        pass

    monkeypatch.setattr(past_mode.asyncio, "sleep", fake_sleep)

    async def always_failing(client, database, source_id, target_id, cfgs, logger, total=None):
        raise MediaDownloadError("t.me/c/1/2: exhausted")  # no message_id

    monkeypatch.setattr(past_mode, "_replay_direction", always_failing)

    with pytest.raises(MediaDownloadError):
        run(
            past_mode._replay_with_retry(
                object(), run(InMemoryDatabase()), SRC, TGT,
                [_cfg(PastModeConfig(full_history=True, send_delay=0))], _LOG,
            )
        )


def test_replay_resumes_from_checkpoint(monkeypatch):
    db = run(InMemoryDatabase())
    run(db.set_past_mode_checkpoint(SRC, TGT, 2))
    run(db.insert_batch([MirrorMessage(2, SRC, 902, TGT)]))
    msgs = [_msg(i) for i in range(1, 6)]
    calls, db = _run_replay(
        monkeypatch, msgs, PastModeConfig(full_history=True, send_delay=0), db=db
    )
    assert calls == [("new", 3), ("new", 4), ("new", 5)]  # min_id=2 is exclusive


def test_replay_multi_topic_single_pass(monkeypatch):
    """A pair with several topic-directions is replayed in ONE history pass;
    the processor receives all the pair's cfgs and the checkpoint advances once."""
    seen_mappings = []
    calls = []

    class Rec:
        def __init__(self, **kw):
            seen_mappings.append(kw["chat_mapping"][SRC][TGT])

        async def new_message(self, chat, msg, link):
            calls.append(msg.id)

        async def new_album(self, chat, album, link):
            calls.append(tuple(m.id for m in album))

    monkeypatch.setattr(past_mode, "EventProcessor", Rec)
    db = run(InMemoryDatabase())
    cfgs = [
        _cfg(PastModeConfig(full_history=True, send_delay=0), from_topic_id=2),
        _cfg(PastModeConfig(full_history=True, send_delay=0), from_topic_id=3),
    ]
    processed = run(
        past_mode._replay_direction(
            FakeClient([_msg(1), _msg(2), _msg(3)]), db, SRC, TGT, cfgs, _LOG
        )
    )
    assert seen_mappings == [cfgs]  # one processor, both topic cfgs, one pass
    assert calls == [1, 2, 3]
    assert processed == 3
    assert run(db.get_past_mode_checkpoint(SRC, TGT)) == 3


class _NoopProcessor:
    def __init__(self, **kw):
        pass

    async def new_message(self, chat, msg, link):
        pass

    async def new_album(self, chat, album, link):
        pass


def test_replay_reuses_passed_total(monkeypatch):
    """When _run passes `total`, _replay_direction must not re-fetch it."""
    limit0_calls = []

    class CountingClient(FakeClient):
        async def get_messages(self, entity, limit=None, **kw):
            if limit == 0:
                limit0_calls.append(entity)
            return await super().get_messages(entity, limit=limit, **kw)

    monkeypatch.setattr(past_mode, "EventProcessor", _NoopProcessor)
    db = run(InMemoryDatabase())
    run(past_mode._replay_direction(
        CountingClient([_msg(1), _msg(2)]), db, SRC, TGT,
        [_cfg(PastModeConfig(full_history=True, send_delay=0))], _LOG, total=99,
    ))
    assert limit0_calls == []


def test_replay_mixed_strategies_warns(monkeypatch, caplog):
    monkeypatch.setattr(past_mode, "EventProcessor", _NoopProcessor)
    db = run(InMemoryDatabase())
    cfgs = [
        _cfg(PastModeConfig(full_history=True, send_delay=0), from_topic_id=2),
        _cfg(PastModeConfig(last_n=5, send_delay=0), from_topic_id=3),
    ]
    with caplog.at_level(logging.WARNING):
        run(past_mode._replay_direction(FakeClient([_msg(1)]), db, SRC, TGT, cfgs, _LOG))
    assert any("different past_mode strategies" in r.message for r in caplog.records)


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
        client, db, {(SRC, TGT): [_cfg(PastModeConfig(full_history=True, send_delay=0))]},
        _LOG,
    ))

    assert len(client.edits) == 1
    entity, message_id, _text, ents = client.edits[0]
    assert (entity, message_id) == (TGT, 910)
    assert ents[0].url == private_message_link(TGT, 907)


class _BatchRecordingClient(_EditFakeClient):
    def __init__(self, src_messages):
        super().__init__(src_messages)
        self.batch_sizes = []

    async def get_messages(self, entity, ids=None, limit=None, **kw):
        if ids is not None:
            self.batch_sizes.append(len(ids))
        return await super().get_messages(entity, ids=ids, limit=limit, **kw)


def test_edit_links_pass_streams_source_messages_in_batches(monkeypatch):
    # 150 mirrors -> the source fetch must be split into 100 + 50, and a
    # rewritable link in either half is still repointed (no master list).
    db = run(InMemoryDatabase(max_capacity=1000))  # avoid LRU eviction mid-test
    run(db.insert_batch(
        [MirrorMessage(oid, SRC, oid + 900, TGT) for oid in range(1, 151)]
    ))

    src_peer = -SRC - 1000000000000

    def _linker(mid, points_to):
        return types.Message(
            id=mid,
            peer_id=types.PeerChannel(1),
            message="link",
            entities=[types.MessageEntityTextUrl(
                offset=0, length=4, url=f"https://t.me/c/{src_peer}/{points_to}"
            )],
        )

    src = [types.Message(id=i, peer_id=types.PeerChannel(1), message="x")
           for i in range(1, 151)]
    src[9] = _linker(10, 149)     # in the first batch
    src[139] = _linker(140, 150)  # in the second batch
    client = _BatchRecordingClient(src)

    run(past_mode._edit_links_pass(
        client, db, {(SRC, TGT): [_cfg(PastModeConfig(full_history=True, send_delay=0))]},
        _LOG,
    ))

    assert client.batch_sizes == [100, 50]
    assert sorted(m for _e, m, _t, _ents in client.edits) == [910, 1040]
