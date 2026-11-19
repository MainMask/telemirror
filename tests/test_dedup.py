"""dedup_hours (🧬 Без повторов): a post the target already got from another
source post within the window isn't sent again — the same post again (a
retry) is."""

import asyncio
import logging
import time

from telethon.tl import types

import telemirror.mirroring as mirroring
from telemirror.dedup import fingerprint
from telemirror.directions import DirectionConfig
from telemirror.messagefilters import EmptyMessageFilter
from telemirror.mirroring import EventProcessor
from telemirror.outcomes import DUPLICATE, SENT
from telemirror.storage import InMemoryDatabase, MirrorMessage
from tests.conftest import make_message, run

A, B = -1001000000001, -1001000000002
T1, T2 = -1002000000001, -1002000000002
LONG = "Новость дня: что-то очень важное случилось"


def _photo(pid):
    return types.MessageMediaPhoto(photo=types.Photo(id=pid, access_hash=0, file_reference=b"", date=None,
                                                     sizes=[], dc_id=1))


def _msg(text, mid=1, media=None):
    m = make_message(text, media=media)
    m.id = mid
    return m


def test_fingerprint_rules():
    assert fingerprint([_msg(LONG)]) == fingerprint([_msg("  " + LONG.upper().replace(" ", "\n  "))])
    assert fingerprint([_msg("коротко")]) is None
    assert fingerprint([_msg("", media=_photo(5))]) == fingerprint([_msg("", media=_photo(5))])
    # a recurring caption under another photo isn't a repeat
    assert fingerprint([_msg(LONG, media=_photo(5))]) != fingerprint([_msg(LONG, media=_photo(6))])
    assert fingerprint([_msg("", media=_photo(5)), _msg("", media=_photo(6))]) == \
        fingerprint([_msg("", media=_photo(6)), _msg("", media=_photo(5))])
    assert fingerprint([_msg("x", media=types.MessageMediaUnsupported())]) is None


class _Sink:
    def __init__(self):
        self.states = []

    def record(self, chat_id, ids, link, outcomes):
        self.states.append([(t.chat, t.state) for t in outcomes.targets])


def _cfg(hours):
    return DirectionConfig(disable_delete=False, disable_edit=False, filters=EmptyMessageFilter(),
                           dedup_hours=hours)


def _setup(monkeypatch, hours=24):
    sent = []

    async def send(client, entity, message, **kw):
        sent.append(entity)
        return types.Message(id=len(sent), peer_id=types.PeerChannel(1), message="x")

    monkeypatch.setattr(mirroring, "send_message", send)
    sink = _Sink()
    db = run(InMemoryDatabase())
    proc = EventProcessor(chat_mapping={A: {T1: [_cfg(hours)], T2: [_cfg(hours)]}, B: {T1: [_cfg(hours)]}},
                          database=db, client=object(), logger=logging.getLogger("test.dedup"), sink=sink)
    return proc, db, sent, sink


def test_repeat_from_another_source_is_skipped_only_where_it_arrived(monkeypatch):
    proc, db, sent, sink = _setup(monkeypatch)
    run(proc.new_message(B, _msg(LONG, mid=7), "b7"))  # B → T1 only
    run(proc.new_message(A, _msg(LONG, mid=3), "a3"))  # A → T1 (repeat) and T2 (new there)
    assert sent == [T1, T2]
    assert sink.states[-1] == [(T1, DUPLICATE), (T2, SENT)]


def test_the_same_post_again_is_not_a_repeat(monkeypatch):
    proc, db, sent, sink = _setup(monkeypatch)
    run(proc.new_message(B, _msg(LONG, mid=7), "b7"))
    run(db.delete_bindings_for_mirror(T1))  # as if T1 had missed it: a retry sends it again
    run(proc.new_message(B, _msg(LONG, mid=7), "b7"))
    assert sent == [T1, T1]


def test_off_and_after_the_window(monkeypatch):
    proc, db, sent, _ = _setup(monkeypatch, hours=0)
    run(proc.new_message(B, _msg(LONG, mid=7), "b7"))
    run(proc.new_message(A, _msg(LONG, mid=3), "a3"))
    assert sent == [T1, T1, T2]  # off: nothing remembered, nothing skipped

    proc, db, sent, _ = _setup(monkeypatch, hours=1)
    run(db.remember_fingerprint(T1, None, fingerprint([_msg(LONG)]), B, [7], int(time.time() - 7200)))
    run(proc.new_message(A, _msg(LONG, mid=3), "a3"))
    assert sent == [T1, T2]


def test_album_repeat(monkeypatch):
    sent = []

    async def send_file(client, entity, caption, file, **kw):
        sent.append(entity)
        return [types.Message(id=len(sent) * 10 + n, peer_id=types.PeerChannel(1), message="")
                for n in range(len(file))]

    monkeypatch.setattr(mirroring, "send_file", send_file)
    proc = EventProcessor(chat_mapping={A: {T1: [_cfg(24)]}, B: {T1: [_cfg(24)]}},
                          database=run(InMemoryDatabase()), client=object(), logger=logging.getLogger("t"))
    run(proc.new_album(B, [_msg("", 1, _photo(5)), _msg("", 2, _photo(6))], "b"))
    run(proc.new_album(A, [_msg("", 8, _photo(6)), _msg("", 9, _photo(5))], "a"))
    assert sent == [T1]


def test_prune_forgets_old_fingerprints():
    db = run(InMemoryDatabase())
    run(db.remember_fingerprint(T1, None, "f", B, [1], 100))
    run(db.remember_fingerprint(T1, None, "f", B, [2], 300))
    run(db.prune_fingerprints(200, [B], [T1]))
    assert run(db.seen_fingerprint(T1, None, "f", 0, A, [1]))
    assert not run(db.seen_fingerprint(T1, None, "f", 0, B, [2]))  # only itself left


def test_prune_keeps_what_another_project_remembered(monkeypatch):
    """Regression: the database is shared by every project — a mirror with a
    1-hour window used to prune another project's 48-hour fingerprints, and
    that project's repeats got through. Now only its own rows (its sources
    into its targets) are pruned."""
    C, T3 = -1001000000003, -1002000000003  # another project's source and target
    proc, db, _, _ = _setup(monkeypatch, hours=1)
    two_hours_ago = int(time.time() - 7200)
    run(db.remember_fingerprint(T3, None, "theirs", C, [1], two_hours_ago))
    run(db.remember_fingerprint(T1, None, "theirs into ours", C, [2], two_hours_ago))
    run(db.remember_fingerprint(T1, None, "ours", B, [3], two_hours_ago))
    run(proc.new_message(A, _msg(LONG, mid=4), "a4"))  # sends → the hourly prune
    assert run(db.seen_fingerprint(T3, None, "theirs", 0, A, [0]))
    assert run(db.seen_fingerprint(T1, None, "theirs into ours", 0, A, [0]))
    assert not run(db.seen_fingerprint(T1, None, "ours", 0, A, [0]))


def test_the_same_post_from_two_sources_at_once_is_sent_once(monkeypatch):
    """Regression: each update is its own task — two sources posting the same
    at once both checked before either had sent (the fingerprint is remembered
    only after the send), and the target got it twice."""
    sent = []

    async def send(client, entity, message, **kw):
        await asyncio.sleep(0)  # the upload: the other post's check runs meanwhile
        sent.append(entity)
        return types.Message(id=len(sent), peer_id=types.PeerChannel(1), message="x")

    proc, _, _, sink = _setup(monkeypatch)
    monkeypatch.setattr(mirroring, "send_message", send)

    async def both():
        await asyncio.gather(proc.new_message(B, _msg(LONG, mid=7), "b7"),
                             proc.new_message(A, _msg(LONG, mid=3), "a3"))

    run(both())
    assert sorted(sent) == sorted([T1, T2])
    assert proc._dedup_turns == {}  # nothing left behind


def test_a_failed_first_copy_does_not_hold_back_the_second(monkeypatch):
    """Better twice than lost: the first copy failing, the same post from the
    other source still goes."""
    calls = []

    async def send(client, entity, message, **kw):
        await asyncio.sleep(0)
        calls.append(entity)
        if len(calls) == 1:
            raise RuntimeError("no")
        return types.Message(id=len(calls), peer_id=types.PeerChannel(1), message="x")

    proc, _, _, sink = _setup(monkeypatch)
    monkeypatch.setattr(mirroring, "send_message", send)

    async def both():
        await asyncio.gather(proc.new_message(B, _msg(LONG, mid=7), "b7"),
                             proc.new_message(A, _msg(LONG, mid=3), "a3"))

    run(both())
    assert sorted(calls) == sorted([T1, T1, T2])


def test_a_source_without_dedup_does_not_hold_back_one_with_it(monkeypatch):
    """A source whose directions don't dedup takes no turn: the same post from
    a source that does isn't kept waiting for its fan-out (its send delays)."""
    C, T9 = -1001000000003, -1002000000009
    order = []
    gate = asyncio.Event()

    async def send(client, entity, message, **kw):
        if entity == T9:
            await gate.wait()  # C's slow fan-out
        order.append(entity)
        if entity == T1:
            gate.set()
        return types.Message(id=len(order), peer_id=types.PeerChannel(1), message="x")

    monkeypatch.setattr(mirroring, "send_message", send)
    proc = EventProcessor(chat_mapping={C: {T9: [_cfg(0)]}, A: {T1: [_cfg(24)]}},
                          database=run(InMemoryDatabase()), client=object(), logger=logging.getLogger("t"))

    async def both():
        await asyncio.wait_for(asyncio.gather(proc.new_message(C, _msg(LONG, mid=1), "c1"),
                                              proc.new_message(A, _msg(LONG, mid=2), "a2")), 2)

    run(both())
    assert order == [T1, T9]


def test_a_deleted_copy_is_no_reason_to_skip_the_post_again(monkeypatch):
    """Regression: source A's post was deleted — and its copy with it — but its
    fingerprint stayed: the same post from source B within the window was a
    «repeat» of a post the channel no longer had. Where the direction keeps
    copies (disable_delete), the copy stays, so its fingerprint does too."""
    class _Client:
        async def delete_messages(self, entity, message_ids):
            pass

    sent = []

    async def send(client, entity, message, **kw):
        sent.append(entity)
        return types.Message(id=len(sent), peer_id=types.PeerChannel(1), message="x")

    monkeypatch.setattr(mirroring, "send_message", send)
    keep = DirectionConfig(disable_delete=True, disable_edit=False, filters=EmptyMessageFilter(), dedup_hours=24)
    proc = EventProcessor(chat_mapping={A: {T1: [_cfg(24)], T2: [keep]}, B: {T1: [_cfg(24)], T2: [_cfg(24)]}},
                          database=run(InMemoryDatabase()), client=_Client(), logger=logging.getLogger("t"))
    run(proc.new_message(A, _msg(LONG, mid=3), "a3"))
    run(proc.delete_message(A, [3]))  # deleted from T1; T2 keeps its copy
    run(proc.new_message(B, _msg(LONG, mid=7), "b7"))
    assert sent == [T1, T2, T1]


def test_an_album_is_forgotten_only_once_its_whole_copy_is_deleted(monkeypatch):
    """Regression: an album's fingerprint was kept under its first item only —
    deleting that one item forgot it (the other copies still in the channel,
    the same album from another source sent again), deleting all the others
    kept it."""
    class _Client:
        async def delete_messages(self, entity, message_ids):
            pass

    sent = []

    async def send_file(client, entity, caption, file, **kw):
        sent.append(entity)
        return [types.Message(id=len(sent) * 10 + n, peer_id=types.PeerChannel(1), message="")
                for n in range(len(file))]

    monkeypatch.setattr(mirroring, "send_file", send_file)
    proc = EventProcessor(chat_mapping={A: {T1: [_cfg(24)]}, B: {T1: [_cfg(24)]}},
                          database=run(InMemoryDatabase()), client=_Client(), logger=logging.getLogger("t"))
    album = [_msg("", 1, _photo(5)), _msg("", 2, _photo(6))]
    run(proc.new_album(B, album, "b"))
    run(proc.delete_message(B, [1]))  # one item: the copy of the other is still there
    run(proc.new_album(A, [_msg("", 8, _photo(5)), _msg("", 9, _photo(6))], "a"))
    assert sent == [T1]
    run(proc.delete_message(B, [2]))  # the whole copy gone now
    run(proc.new_album(A, [_msg("", 8, _photo(5)), _msg("", 9, _photo(6))], "a"))
    assert sent == [T1, T1]


def test_an_album_again_is_not_a_repeat_of_itself():
    """Remembered under each item: the same album again (a retry) excludes them all."""
    db = run(InMemoryDatabase())
    run(db.remember_fingerprint(T1, None, "f", B, [1, 2], 100))
    assert not run(db.seen_fingerprint(T1, None, "f", 0, B, [1, 2]))
    assert run(db.seen_fingerprint(T1, None, "f", 0, A, [1, 2]))


class _Deleting:
    async def delete_messages(self, entity, message_ids):
        pass


def test_a_kept_copy_keeps_its_fingerprint_when_deleted_together_with_another():
    """Regression: the topics losing a copy were pooled per channel, and every
    deleted id forgotten in each — a post whose copy its direction keeps
    (disable_delete), deleted along with one whose copy goes, lost its
    fingerprint too, and its repeat from another source was sent again."""
    X, Y, T = 10, 20, 30  # source topics; the target's topic
    keep = DirectionConfig(disable_delete=True, disable_edit=False, filters=EmptyMessageFilter(),
                           from_topic_id=X, to_topic_id=T, dedup_hours=24)
    drop = DirectionConfig(disable_delete=False, disable_edit=False, filters=EmptyMessageFilter(),
                           from_topic_id=Y, to_topic_id=T, dedup_hours=24)
    db = run(InMemoryDatabase())
    proc = EventProcessor(chat_mapping={A: {T1: [keep, drop]}}, database=db, client=_Deleting(),
                          logger=logging.getLogger("t"))
    run(db.insert_batch([MirrorMessage(1, A, 101, T1, T, X), MirrorMessage(2, A, 102, T1, T, Y)]))
    run(db.remember_fingerprint(T1, T, "p", A, [1], int(time.time())))
    run(db.remember_fingerprint(T1, T, "q", A, [2], int(time.time())))
    run(proc.delete_message(A, [1, 2]))
    assert run(db.seen_fingerprint(T1, T, "p", 0, B, [9]))  # its copy is still there
    assert not run(db.seen_fingerprint(T1, T, "q", 0, B, [9]))


def test_one_channel_failing_to_forget_does_not_keep_the_others():
    """Regression: one try around every channel — the first failure kept the
    fingerprints of the channels after it, their copies deleted."""
    class _Db(InMemoryDatabase):
        async def forget_fingerprints(self, target, topic, original_channel, original_ids):
            if target == T1:
                raise RuntimeError("db")
            await super().forget_fingerprints(target, topic, original_channel, original_ids)

    db = run(_Db())
    proc = EventProcessor(chat_mapping={A: {T1: [_cfg(24)], T2: [_cfg(24)]}}, database=db,
                          client=_Deleting(), logger=logging.getLogger("t"))
    run(db.insert_batch([MirrorMessage(1, A, 101, T1), MirrorMessage(1, A, 201, T2)]))
    for target in (T1, T2):
        run(db.remember_fingerprint(target, None, "f", A, [1], int(time.time())))
    run(proc.delete_message(A, [1]))
    assert not run(db.seen_fingerprint(T2, None, "f", 0, B, [9]))
