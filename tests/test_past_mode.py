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


def test_integrity_keeps_checkpoint_below_max_mirrored():
    db = run(InMemoryDatabase())
    run(db.set_past_mode_checkpoint(SRC, TGT, 10))
    run(db.insert_batch([MirrorMessage(oid, SRC, oid + 900, TGT) for oid in (5, 42)]))
    # checkpoint 10 < max mirrored 42: NOT rolled forward — already-mirrored
    # messages past the checkpoint are skipped per target by new_message's
    # own dedup, while anything unmirrored in between still gets replayed.
    assert run(past_mode._integrity_check(db, SRC, TGT, _LOG)) == (10, 2)
    assert run(db.get_past_mode_checkpoint(SRC, TGT)) == 10


def test_integrity_does_not_skip_history_after_live_mirror_ran():
    """Backfill interrupted at 50, then main.py mirrored a new post 9000 for
    the same pair: resuming must continue from 50, not jump to 9000 and
    silently skip 51..8999."""
    db = run(InMemoryDatabase(max_capacity=1000))
    run(db.insert_batch([MirrorMessage(oid, SRC, oid + 1000, TGT) for oid in range(1, 51)]))
    run(db.set_past_mode_checkpoint(SRC, TGT, 50))
    run(db.insert(MirrorMessage(9000, SRC, 5000, TGT)))  # live mirror's row
    assert run(past_mode._integrity_check(db, SRC, TGT, _LOG)) == (50, 51)
    assert run(db.get_past_mode_checkpoint(SRC, TGT)) == 50


def test_integrity_keeps_healthy_checkpoint():
    db = run(InMemoryDatabase())
    run(db.set_past_mode_checkpoint(SRC, TGT, 99))
    run(db.insert_batch([MirrorMessage(42, SRC, 942, TGT)]))
    assert run(past_mode._integrity_check(db, SRC, TGT, _LOG)) == (99, 1)


def test_integrity_dedupes_mirror_count_by_source_message():
    """A source message reached by two overlapping direction configs (e.g. a
    catch-all from_topic_id=None plus a topic-scoped one to the same target)
    produces two MirrorMessage rows for the same original_id. mirror_count
    must count distinct source messages, not raw rows, or a bounded last_n
    resume's budget (last_n - mirrors_done) undercounts and stops early."""
    db = run(InMemoryDatabase())
    run(db.set_past_mode_checkpoint(SRC, TGT, 42))
    run(db.insert_batch([
        MirrorMessage(42, SRC, 942, TGT, mirror_topic_id=None),
        MirrorMessage(42, SRC, 943, TGT, mirror_topic_id=7),
    ]))
    assert run(past_mode._integrity_check(db, SRC, TGT, _LOG)) == (42, 1)


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


def test_replay_last_n_buffer_does_not_split_album_at_boundary(monkeypatch):
    """A first-run (no checkpoint) last_n buffer must never land mid-album:
    if the last_n raw-message cutoff would fall inside a grouped_id run, the
    whole album must still be included, not just its newest members."""
    msgs = [_msg(i) for i in range(1, 7)] + [
        _msg(7, grouped_id=99),
        _msg(8, grouped_id=99),
        _msg(9, grouped_id=99),
        _msg(10),
    ]
    # last_n=3 would, with a hard cutoff, only grab {10, 9, 8} — landing
    # inside the 7/8/9 album and silently dropping message 7.
    calls, db = _run_replay(monkeypatch, msgs, PastModeConfig(last_n=3, send_delay=0))
    assert calls == [("album", (7, 8, 9)), ("new", 10)]
    assert run(db.get_past_mode_checkpoint(SRC, TGT)) == 10


def test_replay_last_n_resume_does_not_split_album(monkeypatch):
    """A bounded last_n resume must stop after `iter_total` complete
    messages/albums, never mid-album: a hard iter_messages(limit=...) cutoff
    could otherwise land between an album's members, since an album is only
    known complete once iter_message_groups sees the next non-matching
    message."""
    db = run(InMemoryDatabase())
    run(db.set_past_mode_checkpoint(SRC, TGT, 10))
    run(db.insert_batch([MirrorMessage(oid, SRC, oid + 900, TGT) for oid in (8, 9)]))
    # last_n=3, mirrors_done=2 -> iter_total=1: exactly one more group to process.
    msgs = [_msg(11, grouped_id=5), _msg(12, grouped_id=5), _msg(13)]
    calls, db = _run_replay(
        monkeypatch, msgs, PastModeConfig(last_n=3, send_delay=0), db=db
    )
    assert calls == [("album", (11, 12))]
    assert run(db.get_past_mode_checkpoint(SRC, TGT)) == 12


def test_replay_last_n_resume_does_not_compound_across_albums(monkeypatch):
    """A bounded last_n resume must stop as soon as the raw-message budget is
    met, not after the same number of *groups* — otherwise several
    consecutive albums after the checkpoint each count as "one group" and the
    budget is overshot by every album's size instead of just the last one's."""
    db = run(InMemoryDatabase())
    run(db.set_past_mode_checkpoint(SRC, TGT, 10))
    run(db.insert_batch([MirrorMessage(oid, SRC, oid + 900, TGT) for oid in (8, 9)]))
    # last_n=4, mirrors_done=2 -> iter_total=2: budget for 2 more raw messages.
    msgs = [
        _msg(11, grouped_id=5), _msg(12, grouped_id=5), _msg(13, grouped_id=5),
        _msg(14, grouped_id=6), _msg(15, grouped_id=6), _msg(16, grouped_id=6),
    ]
    calls, db = _run_replay(
        monkeypatch, msgs, PastModeConfig(last_n=4, send_delay=0), db=db
    )
    assert calls == [("album", (11, 12, 13))]
    assert run(db.get_past_mode_checkpoint(SRC, TGT)) == 13


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
    """Serves source messages for SRC and the mirrors' current content for
    TGT. A mirror not given in ``mirrors`` holds stale text (not yet fixed),
    so the pass has something to edit."""

    def __init__(self, src_messages, mirrors=None):
        self._src = {m.id: m for m in src_messages}
        self._mirrors = mirrors or {}
        self.edits = []
        self.edit_kwargs = []

    async def get_messages(self, entity, ids=None, limit=None, **kw):
        if ids is not None and entity == TGT:
            return [
                self._mirrors.get(i)
                or types.Message(id=i, peer_id=types.PeerChannel(2), message="stale")
                for i in ids
            ]
        if ids is not None:
            return [self._src.get(i) for i in ids]
        return _Total(len(self._src))

    async def edit_message(self, entity, message, text, formatting_entities=None, **kw):
        self.edits.append((entity, message, text, formatting_entities))
        self.edit_kwargs.append(kw)


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
        if ids is not None and entity != TGT:  # source batches only
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


def test_edit_links_pass_fixes_every_mirror_of_a_multi_topic_source_message():
    """A source message mirrored into TGT via more than one topic-scoped
    config shares one `original_id` across several `MirrorMessage` rows
    (`binding_id` has no topic column — multi-topic-per-pair replay is a
    supported feature, see REVIEW.md Batch C). Keying the lookup dict by
    `original_id` alone (pre-fix) collapsed those rows to one, so only one
    topic's mirror ever got its broken link fixed; the other kept it stale
    forever (this pass is best-effort, run-once)."""
    db = run(InMemoryDatabase())
    # message 10 mirrored into TGT twice (two topics): 910 and 920. Both must
    # get their link fixed.
    run(db.insert_batch([
        MirrorMessage(10, SRC, 910, TGT),
        MirrorMessage(10, SRC, 920, TGT),
        MirrorMessage(7, SRC, 907, TGT),
    ]))

    src_peer = -SRC - 1000000000000
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

    assert sorted(message_id for _e, message_id, _t, _ents in client.edits) == [910, 920]


def test_edit_links_pass_resolves_topic_scoped_mirror():
    """Both the edited mirror and the referenced mirror carry a real
    `mirror_topic_id` (a topic-scoped direction) — the link-fixing pass must
    resolve the reference using *that mirror's own* topic, not a (channel,
    None) lookup that would never match a topic-scoped row."""
    from telemirror.misc.links import private_message_link

    db = run(InMemoryDatabase())
    run(db.insert_batch([
        MirrorMessage(10, SRC, 910, TGT, mirror_topic_id=5),
        MirrorMessage(7, SRC, 907, TGT, mirror_topic_id=5),
    ]))

    src_peer = -SRC - 1000000000000
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


# --- _edit_links_pass: compares with the mirror, keeps text filters (Pass 21)

def _linking_source(points_to=7, text="see"):
    src_peer = -SRC - 1000000000000
    return types.Message(
        id=10,
        peer_id=types.PeerChannel(1),
        message=text,
        entities=[types.MessageEntityTextUrl(
            offset=0, length=3, url=f"https://t.me/c/{src_peer}/{points_to}"
        )],
    )


def _pass_db():
    db = run(InMemoryDatabase())
    run(db.insert_batch([
        MirrorMessage(10, SRC, 910, TGT),
        MirrorMessage(7, SRC, 907, TGT),
    ]))
    return db


def _edit_pass(client, db, filters=None):
    cfg = _cfg(PastModeConfig(full_history=True, send_delay=0))
    if filters is not None:
        cfg = DirectionConfig(
            disable_delete=False, disable_edit=False, filters=filters,
            past_mode=cfg.past_mode,
        )
    run(past_mode._edit_links_pass(client, db, {(SRC, TGT): [cfg]}, _LOG))


def test_edit_links_pass_skips_mirror_that_already_has_the_link():
    """The link was resolved when the mirror was sent (the referenced message
    was mirrored earlier): re-sending the identical edit only draws a
    MessageNotModifiedError and burns an edit request on every run."""
    from telemirror.misc.links import private_message_link

    already = types.Message(
        id=910, peer_id=types.PeerChannel(2), message="see",
        entities=[types.MessageEntityTextUrl(
            offset=0, length=3, url=private_message_link(TGT, 907)
        )],
    )
    client = _EditFakeClient([_linking_source()], mirrors={910: already})
    _edit_pass(client, _pass_db())
    assert client.edits == []


def test_edit_links_pass_keeps_text_filter_output():
    """The edit is built through the direction's filter chain, same as
    new_message — a KeywordReplaceFilter's replacement isn't reverted to
    the raw source text."""
    from telemirror.messagefilters import KeywordReplaceFilter

    client = _EditFakeClient([_linking_source()])
    _edit_pass(client, _pass_db(), filters=KeywordReplaceFilter({"see": "look"}))
    assert [(m, t) for _e, m, t, _ents in client.edits] == [(910, "look")]


def test_edit_links_pass_respects_a_discarding_filter():
    from telemirror.messagefilters import SkipWithKeywordsFilter

    client = _EditFakeClient([_linking_source()])
    _edit_pass(client, _pass_db(), filters=SkipWithKeywordsFilter({"see"}))
    assert client.edits == []


def test_edit_links_pass_skips_split_caption_mirror():
    """A >1024 caption was split at send time (media with an empty caption +
    an untracked text reply); the caption can't take the full text back."""
    long_src = _linking_source(text="see" + "x" * 1100)
    split_mirror = types.Message(
        id=910, peer_id=types.PeerChannel(2), message="",
        media=types.MessageMediaPhoto(photo=types.PhotoEmpty(id=1)),
    )
    client = _EditFakeClient([long_src], mirrors={910: split_mirror})
    _edit_pass(client, _pass_db())
    assert client.edits == []


def test_edit_links_pass_fixes_long_caption_sent_whole():
    """A Premium mirror account sends a >1024 caption whole (no split): its
    stale link must still be fixed — only an *empty*-caption media mirror
    is a split one."""
    long_src = _linking_source(text="see" + "x" * 1100)
    whole_mirror = types.Message(
        id=910, peer_id=types.PeerChannel(2), message="see" + "x" * 1100,
        media=types.MessageMediaPhoto(photo=types.PhotoEmpty(id=1)),
    )
    client = _EditFakeClient([long_src], mirrors={910: whole_mirror})
    _edit_pass(client, _pass_db())
    assert [m for _e, m, _t, _ents in client.edits] == [910]


@pytest.mark.parametrize("has_preview", [False, True])
def test_edit_links_pass_keeps_the_mirrors_link_preview_state(has_preview):
    """Telethon's edit_message defaults to link_preview=True: without an
    explicit value the edit would add a preview to a mirror that has none."""
    mirror = types.Message(
        id=910, peer_id=types.PeerChannel(2), message="stale",
        media=types.MessageMediaWebPage(webpage=types.WebPageEmpty(id=1))
        if has_preview else None,
    )
    client = _EditFakeClient([_linking_source()], mirrors={910: mirror})
    _edit_pass(client, _pass_db())
    assert [kw.get("link_preview") for kw in client.edit_kwargs] == [has_preview]


def test_edit_links_pass_uses_each_mirrors_own_direction_filters():
    """Two topic directions of one pair with different filter chains: each
    mirror's edit goes through the chain of the direction that produced it
    (matched by its source/mirror topic), not the pair's first one."""
    from telemirror.messagefilters import KeywordReplaceFilter

    pm = PastModeConfig(full_history=True, send_delay=0)
    topic5 = DirectionConfig(
        disable_delete=False, disable_edit=False,
        filters=KeywordReplaceFilter({"see": "look"}),
        from_topic_id=5, to_topic_id=50, past_mode=pm,
        fallback_link_url="https://t.me/Fallback",
    )
    topic6 = DirectionConfig(
        disable_delete=False, disable_edit=False, filters=EmptyMessageFilter(),
        from_topic_id=6, to_topic_id=60, past_mode=pm,
        fallback_link_url="https://t.me/Fallback",
    )
    db = run(InMemoryDatabase())
    run(db.insert_batch([
        MirrorMessage(10, SRC, 910, TGT, mirror_topic_id=60, source_topic_id=6),
    ]))
    client = _EditFakeClient([_linking_source(points_to=999)])
    run(past_mode._edit_links_pass(client, db, {(SRC, TGT): [topic5, topic6]}, _LOG))
    assert [(m, t) for _e, m, t, _ents in client.edits] == [(910, "see")]
