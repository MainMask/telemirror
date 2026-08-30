"""Sign-off coverage for telemirror/storage.py InMemoryDatabase (the DB used in
every test and in dev). PostgresDatabase needs a live server and is reviewed by
inspection only (see REVIEW.md)."""

from telemirror.storage import InMemoryDatabase, MirrorMessage
from tests.conftest import run

SRC = -1001000000000
DST_A = -1002000000001
DST_B = -1002000000002


def _mm(oid, mid, mchan=DST_A, ochan=SRC):
    return MirrorMessage(
        original_id=oid, original_channel=ochan, mirror_id=mid, mirror_channel=mchan
    )


def test_insert_batch_and_get_messages_roundtrip():
    db = run(InMemoryDatabase())
    run(db.insert_batch([_mm(10, 100, DST_A), _mm(10, 101, DST_B)]))

    got = run(db.get_messages(10, SRC))
    assert {m.mirror_channel: m.mirror_id for m in got} == {DST_A: 100, DST_B: 101}
    assert run(db.get_messages(999, SRC)) == []


def test_get_messages_batch_spans_ids():
    db = run(InMemoryDatabase())
    run(db.insert_batch([_mm(1, 11), _mm(2, 22), _mm(3, 33)]))
    got = run(db.get_messages_batch([1, 3, 999], SRC))
    assert sorted(m.mirror_id for m in got) == [11, 33]


def test_delete_messages_batch_removes_only_named_ids():
    db = run(InMemoryDatabase())
    run(db.insert_batch([_mm(1, 11), _mm(2, 22)]))
    run(db.delete_messages_batch([1], SRC))
    assert run(db.get_messages(1, SRC)) == []
    assert run(db.get_messages(2, SRC))[0].mirror_id == 22


def test_capacity_evicts_oldest_mapping():
    db = run(InMemoryDatabase(max_capacity=4))
    for i in range(10):
        run(db.insert(_mm(i, i * 10)))
    assert run(db.get_messages(0, SRC)) == []      # evicted
    assert run(db.get_messages(9, SRC))[0].mirror_id == 90  # newest kept


def test_get_all_messages_for_channel_is_prefix_exact_not_substring():
    db = run(InMemoryDatabase())
    run(db.insert(_mm(5, 55, ochan=100)))
    run(db.insert(_mm(5, 66, ochan=1000)))
    got = run(db.get_all_messages_for_channel(100))
    assert [m.mirror_id for m in got] == [55]


def test_channel_pair_filter():
    db = run(InMemoryDatabase())
    run(db.insert_batch([_mm(1, 11, DST_A), _mm(1, 12, DST_B)]))
    got = run(db.get_messages_for_channel_pair(SRC, DST_B))
    assert [m.mirror_id for m in got] == [12]


def test_checkpoint_get_set():
    db = run(InMemoryDatabase())
    assert run(db.get_past_mode_checkpoint(SRC, DST_A)) is None
    run(db.set_past_mode_checkpoint(SRC, DST_A, 42))
    assert run(db.get_past_mode_checkpoint(SRC, DST_A)) == 42
    assert run(db.get_past_mode_checkpoint(SRC, DST_B)) is None


def test_broadcast_sync_get_returns_copy_and_delete_works():
    db = run(InMemoryDatabase())
    run(db.set_broadcast_sync(SRC, 1, None))
    run(db.set_broadcast_sync(SRC, 2, 1700000000))

    snapshot = run(db.get_broadcast_sync(SRC))
    assert snapshot == {1: None, 2: 1700000000}
    snapshot[3] = 999  # mutating the returned dict must not leak into storage
    assert 3 not in run(db.get_broadcast_sync(SRC))

    run(db.delete_broadcast_sync(SRC, [1]))
    assert run(db.get_broadcast_sync(SRC)) == {2: 1700000000}
