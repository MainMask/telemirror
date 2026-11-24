"""Sign-off coverage for telemirror/storage.py InMemoryDatabase (the DB used in
every test and in dev). PostgresDatabase against a live server:
tests/test_storage_postgres.py."""

import pytest

from telemirror import storage
from telemirror.storage import InMemoryDatabase, MirrorMessage, PostgresDatabase
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


def test_source_topic_id_roundtrips():
    db = run(InMemoryDatabase())
    run(db.insert_batch([MirrorMessage(
        1, SRC, 100, DST_A, mirror_topic_id=5, source_topic_id=20
    )]))
    got = run(db.get_messages(1, SRC))[0]
    assert (got.mirror_topic_id, got.source_topic_id) == (5, 20)


def test_get_messages_batch_spans_ids():
    db = run(InMemoryDatabase())
    run(db.insert_batch([_mm(1, 11), _mm(2, 22), _mm(3, 33)]))
    got = run(db.get_messages_batch([1, 3, 999], SRC))
    assert sorted(m.mirror_id for m in got) == [11, 33]


def test_delete_messages_for_channels_batch_removes_only_named_ids():
    db = run(InMemoryDatabase())
    run(db.insert_batch([_mm(1, 11), _mm(2, 22)]))
    run(db.delete_messages_for_channels_batch(SRC, {DST_A: [11]}))
    assert run(db.get_messages(1, SRC)) == []
    assert run(db.get_messages(2, SRC))[0].mirror_id == 22


def test_delete_messages_for_channels_batch_is_scoped_to_one_channel():
    db = run(InMemoryDatabase())
    run(db.insert_batch([_mm(1, 11, mchan=DST_A), _mm(1, 12, mchan=DST_B)]))
    run(db.delete_messages_for_channels_batch(SRC, {DST_A: [11]}))
    remaining = run(db.get_messages(1, SRC))
    assert [m.mirror_channel for m in remaining] == [DST_B]


def test_delete_messages_for_channels_batch_is_scoped_to_named_mirror_ids():
    """Two topic-scoped mirrors of the *same* original_id in the *same*
    channel (different mirror_id each) — purging one must not drop the
    other. Scoping by mirror_id (not original_id) is what makes
    `delete_message`'s per-topic purge precise."""
    db = run(InMemoryDatabase())
    run(db.insert_batch([
        _mm(1, 11, mchan=DST_A),
        _mm(1, 12, mchan=DST_A),
    ]))
    run(db.delete_messages_for_channels_batch(SRC, {DST_A: [11]}))
    remaining = run(db.get_messages(1, SRC))
    assert [m.mirror_id for m in remaining] == [12]


def test_delete_messages_for_channels_batch_covers_multiple_channels_in_one_call():
    db = run(InMemoryDatabase())
    run(db.insert_batch([
        _mm(1, 11, mchan=DST_A),
        _mm(1, 12, mchan=DST_B),
        _mm(2, 22, mchan=DST_A),
    ]))
    run(db.delete_messages_for_channels_batch(SRC, {DST_A: [11], DST_B: [12]}))
    assert run(db.get_messages(1, SRC)) == []
    assert run(db.get_messages(2, SRC))[0].mirror_id == 22


def test_capacity_evicts_oldest_mapping():
    db = run(InMemoryDatabase(max_capacity=4))
    for i in range(10):
        run(db.insert_batch([_mm(i, i * 10)]))
    assert run(db.get_messages(0, SRC)) == []      # evicted
    assert run(db.get_messages(9, SRC))[0].mirror_id == 90  # newest kept


def test_get_messages_for_channel_pair_is_prefix_exact_not_substring():
    db = run(InMemoryDatabase())
    run(db.insert_batch([_mm(5, 55, ochan=100)]))
    run(db.insert_batch([_mm(5, 66, ochan=1000)]))
    got = run(db.get_messages_for_channel_pair(100, DST_A))
    assert [m.mirror_id for m in got] == [55]


def test_channel_pair_filter():
    db = run(InMemoryDatabase())
    run(db.insert_batch([_mm(1, 11, DST_A), _mm(1, 12, DST_B)]))
    got = run(db.get_messages_for_channel_pair(SRC, DST_B))
    assert [m.mirror_id for m in got] == [12]


def test_count_mirrored_counts_each_source_message_once():
    db = run(InMemoryDatabase())
    run(db.insert_batch([
        _mm(1, 101), MirrorMessage(1, SRC, 102, DST_A, mirror_topic_id=7),  # one post, two topics
        _mm(2, 103), _mm(3, 104, mchan=DST_B),
    ]))
    assert run(db.count_mirrored(SRC, DST_A, 99)) == 2
    assert run(db.count_mirrored(SRC, DST_A, 1)) == 1  # ids up to 1 only
    assert run(db.count_mirrored(SRC, DST_B, 99)) == 1
    assert run(db.count_mirrored(DST_A, SRC, 99)) == 0


def test_a_failed_start_closes_the_pool(monkeypatch):
    """Regression: the tables failing to be created (the server not ready, no
    rights) left the pool just opened open — the caller got no DB to close."""
    events = []

    class Pool:
        check_connection = None

        def __init__(self, **kw):
            pass

        async def open(self):
            events.append("open")

        async def close(self):
            events.append("close")

    async def no_tables(self):
        raise RuntimeError("permission denied")

    monkeypatch.setattr(storage, "AsyncConnectionPool", Pool)
    monkeypatch.setattr(PostgresDatabase, "_PostgresDatabase__create_tables_if_not_exists", no_tables)
    with pytest.raises(RuntimeError, match="permission denied"):
        run(PostgresDatabase(connection_string="postgresql://x"))
    assert events == ["open", "close"]


class _SchemaCursor:
    """Records the migration's statements; `columns`/`indexes`: what the
    database already has."""

    def __init__(self, columns, indexes):
        self.columns, self.indexes, self.sql = columns, indexes, []
        self._rows = []

    async def execute(self, query, params=None):
        self.sql.append(" ".join(query.split()))
        if "information_schema.columns" in query:
            self._rows = [(c,) for c in self.columns]
        elif "to_regclass" in query:
            self._rows = [(params[0] if params[0] in self.indexes else None,)]

    async def fetchall(self):
        return self._rows

    async def fetchone(self):
        return self._rows[0]


def _migrate(monkeypatch, columns, indexes):
    from contextlib import asynccontextmanager

    cursor = _SchemaCursor(columns, indexes)

    @asynccontextmanager
    async def pg_cursor(self):
        yield cursor

    monkeypatch.setattr(PostgresDatabase, "_PostgresDatabase__pg_cursor", pg_cursor)
    run(PostgresDatabase("postgresql://x")._PostgresDatabase__create_tables_if_not_exists())
    return cursor.sql


_COLUMNS = ("mirror_topic_id", "source_topic_id", "source_media_id")
_INDEXES = ("binding_id_original_idx", "binding_id_channel_pair_idx",
            "post_fingerprint_lookup_idx", "post_fingerprint_created_idx")


def test_migration_on_an_up_to_date_schema_alters_nothing(monkeypatch):
    """ALTER TABLE / CREATE INDEX lock the table even with IF NOT EXISTS: a
    start against an up-to-date schema runs neither."""
    sql = _migrate(monkeypatch, _COLUMNS, _INDEXES)
    assert sql[0].startswith("SELECT pg_advisory_xact_lock(")
    assert not [s for s in sql if s.startswith(("ALTER", "CREATE INDEX"))]


def test_migration_adds_only_what_is_missing(monkeypatch):
    sql = _migrate(monkeypatch, ("source_topic_id",), ("post_fingerprint_created_idx",))
    assert [s for s in sql if s.startswith("ALTER")] == [
        "ALTER TABLE binding_id ADD COLUMN mirror_topic_id bigint",
        "ALTER TABLE binding_id ADD COLUMN source_media_id bigint",
    ]
    assert [s.split()[5] for s in sql if s.startswith("CREATE INDEX")] == list(_INDEXES[:3])


def test_checkpoint_get_set():
    db = run(InMemoryDatabase())
    assert run(db.get_past_mode_checkpoint(SRC, DST_A)) is None
    run(db.set_past_mode_checkpoint(SRC, DST_A, 42))
    assert run(db.get_past_mode_checkpoint(SRC, DST_A)) == 42
    assert run(db.get_past_mode_checkpoint(SRC, DST_B)) is None


def test_delete_past_mode_checkpoint():
    db = run(InMemoryDatabase())
    run(db.set_past_mode_checkpoint(SRC, DST_A, 42))
    run(db.set_past_mode_checkpoint(SRC, DST_B, 7))
    run(db.delete_past_mode_checkpoint(SRC, DST_A))
    assert run(db.get_past_mode_checkpoint(SRC, DST_A)) is None
    assert run(db.get_past_mode_checkpoint(SRC, DST_B)) == 7
    run(db.delete_past_mode_checkpoint(SRC, DST_A))  # absent → no error


def test_drip_state_and_its_reset_with_the_checkpoint():
    db = run(InMemoryDatabase())
    assert run(db.get_drip_state(SRC, DST_A)) == (None, None)
    run(db.set_drip_sent(SRC, DST_A, 100.5))
    run(db.set_drip_done(SRC, DST_A, "last_n=5"))
    run(db.set_drip_sent(SRC, DST_A, 200.0))  # each kept apart from the other
    assert run(db.get_drip_state(SRC, DST_A)) == (200.0, "last_n=5")
    assert run(db.get_drip_state(SRC, DST_B)) == (None, None)
    run(db.set_past_mode_checkpoint(SRC, DST_A, 42))
    run(db.delete_past_mode_checkpoint(SRC, DST_A))  # a cleared target: copied again
    assert run(db.get_drip_state(SRC, DST_A)) == (None, None)


def test_delete_bindings_for_mirror_only_named_channel():
    db = run(InMemoryDatabase())
    run(db.insert_batch([_mm(1, 11, DST_A), _mm(1, 12, DST_B), _mm(2, 22, DST_A)]))
    run(db.delete_bindings_for_mirror(DST_A))
    assert run(db.get_messages(2, SRC)) == []  # only DST_A row → key dropped
    assert [m.mirror_id for m in run(db.get_messages(1, SRC))] == [12]  # DST_B kept


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


def test_source_media_id_roundtrips_and_updates_only_its_mirror():
    db = run(InMemoryDatabase())
    run(db.insert_batch([
        MirrorMessage(1, SRC, 100, DST_A, source_media_id=5),
        MirrorMessage(1, SRC, 100, DST_B, source_media_id=5),  # same mirror_id, other channel
    ]))
    run(db.update_source_media_id(SRC, 1, DST_A, 100, 6))
    got = {m.mirror_channel: m.source_media_id for m in run(db.get_messages(1, SRC))}
    assert got == {DST_A: 6, DST_B: 5}


def test_memory_broadcast_sync_is_bounded():
    """One entry per broadcast post, removed only on a source deletion — in
    memory it must not grow without bound over a long run."""
    db = run(InMemoryDatabase(max_capacity=10))
    for mid in range(100):
        run(db.set_broadcast_sync(-1009, mid, None))
    synced = run(db.get_broadcast_sync(-1009))
    assert len(synced) <= 10 and 99 in synced
