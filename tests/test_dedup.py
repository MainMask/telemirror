"""dedup_hours (🧬 Без повторов): a post the target already got from another
source post within the window isn't sent again — the same post again (a
retry) is."""

import logging
import time

from telethon.tl import types

import telemirror.mirroring as mirroring
from telemirror.dedup import fingerprint
from telemirror.directions import DirectionConfig
from telemirror.messagefilters import EmptyMessageFilter
from telemirror.mirroring import EventProcessor
from telemirror.outcomes import DUPLICATE, SENT
from telemirror.storage import InMemoryDatabase
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
    run(db.remember_fingerprint(T1, None, fingerprint([_msg(LONG)]), B, 7, int(time.time() - 7200)))
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
    run(db.remember_fingerprint(T1, None, "f", B, 1, 100))
    run(db.remember_fingerprint(T1, None, "f", B, 2, 300))
    run(db.prune_fingerprints(200, [B], [T1]))
    assert run(db.seen_fingerprint(T1, None, "f", 0, A, 1))
    assert not run(db.seen_fingerprint(T1, None, "f", 0, B, 2))  # only itself left


def test_prune_keeps_what_another_project_remembered(monkeypatch):
    """Regression: the database is shared by every project — a mirror with a
    1-hour window used to prune another project's 48-hour fingerprints, and
    that project's repeats got through. Now only its own rows (its sources
    into its targets) are pruned."""
    C, T3 = -1001000000003, -1002000000003  # another project's source and target
    proc, db, _, _ = _setup(monkeypatch, hours=1)
    two_hours_ago = int(time.time() - 7200)
    run(db.remember_fingerprint(T3, None, "theirs", C, 1, two_hours_ago))
    run(db.remember_fingerprint(T1, None, "theirs into ours", C, 2, two_hours_ago))
    run(db.remember_fingerprint(T1, None, "ours", B, 3, two_hours_ago))
    run(proc.new_message(A, _msg(LONG, mid=4), "a4"))  # sends → the hourly prune
    assert run(db.seen_fingerprint(T3, None, "theirs", 0, A, 0))
    assert run(db.seen_fingerprint(T1, None, "theirs into ours", 0, A, 0))
    assert not run(db.seen_fingerprint(T1, None, "ours", 0, A, 0))
