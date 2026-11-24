"""PostgresDatabase against a live server — TEST_DATABASE_URL (CI's postgres
service); its cases skip without it. The shared cases run on InMemoryDatabase
too: both backends must answer the same. Each Postgres case gets an empty
schema of its own (``search_path``), dropped afterwards."""

import asyncio
import os

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from telemirror.storage import InMemoryDatabase, MirrorMessage, PostgresDatabase
from tests.conftest import run

URL = os.environ.get("TEST_DATABASE_URL")
needs_postgres = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")
SCHEMA = "telemirror_test"
APP = "telemirror-test"  # the test pool's connections, to tell them from others

SRC = -1001000000000
SRC_B = -1001000000009
DST_A = -1002000000001
DST_B = -1002000000002


@pytest.fixture
def dsn():
    if not URL:
        pytest.skip("TEST_DATABASE_URL not set")
    with psycopg.connect(URL, autocommit=True) as conn:
        conn.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        conn.execute(f"CREATE SCHEMA {SCHEMA}")
    yield make_conninfo(URL, options=f"-csearch_path={SCHEMA}", application_name=APP)
    with psycopg.connect(URL, autocommit=True) as conn:
        conn.execute(f"DROP SCHEMA {SCHEMA} CASCADE")


@pytest.fixture(params=["memory", pytest.param("postgres", marks=needs_postgres)])
def with_db(request):
    """``with_db(scenario)``: runs ``await scenario(db)`` on a fresh database
    of the backend, in one event loop (a pool is bound to its loop)."""
    url = request.getfixturevalue("dsn") if request.param == "postgres" else None

    def go(scenario):
        async def body():
            db = await (PostgresDatabase(url) if url else InMemoryDatabase())
            try:
                return await scenario(db)
            finally:
                await db.close()
        return run(body())

    return go


def _mm(oid, mid, mchan=DST_A, ochan=SRC, topic=None, src_topic=None, media=None):
    return MirrorMessage(oid, ochan, mid, mchan, topic, src_topic, media)


# --- shared: both backends -------------------------------------------------


def test_bindings_roundtrip(with_db):
    async def scenario(db):
        await db.insert_batch([_mm(1, 11, topic=5, src_topic=20, media=7), _mm(1, 12, DST_B),
                               _mm(2, 22)])
        await db.insert_batch([])
        assert await db.get_messages(999, SRC) == []
        one = sorted(await db.get_messages(1, SRC))
        assert one == [_mm(1, 11, topic=5, src_topic=20, media=7), _mm(1, 12, DST_B)]
        batch = sorted(m.mirror_id for m in await db.get_messages_batch([1, 2, 999], SRC))
        assert batch == [11, 12, 22]
        assert await db.get_messages_batch([], SRC) == []
        assert await db.get_messages_batch([1], SRC_B) == []
    with_db(scenario)


def test_delete_is_scoped_by_channel_and_mirror_id(with_db):
    async def scenario(db):
        await db.insert_batch([
            _mm(1, 11, topic=1), _mm(1, 12, topic=2),  # one post, two topics of DST_A
            _mm(1, 13, DST_B), _mm(2, 21), _mm(1, 11, ochan=SRC_B),
        ])
        await db.delete_messages_for_channels_batch(SRC, {})
        await db.delete_messages_for_channels_batch(SRC, {DST_A: [11], DST_B: [13]})
        assert [m.mirror_id for m in await db.get_messages(1, SRC)] == [12]
        assert [m.mirror_id for m in await db.get_messages(2, SRC)] == [21]
        assert [m.mirror_id for m in await db.get_messages(1, SRC_B)] == [11]
    with_db(scenario)


def test_channel_pair_and_count_mirrored(with_db):
    async def scenario(db):
        await db.insert_batch([_mm(1, 101, topic=1), _mm(1, 102, topic=2), _mm(2, 103),
                               _mm(3, 104, DST_B), _mm(4, 105, ochan=SRC_B)])
        assert sorted(m.mirror_id for m in await db.get_messages_for_channel_pair(SRC, DST_A)) \
            == [101, 102, 103]
        assert await db.count_mirrored(SRC, DST_A, 99) == 2  # post 1 once, however many topics
        assert await db.count_mirrored(SRC, DST_A, 1) == 1  # ids up to 1 only
        assert await db.count_mirrored(SRC, DST_B, 99) == 1
        assert await db.count_mirrored(DST_A, SRC, 99) == 0
        await db.delete_bindings_for_mirror(DST_A)
        assert await db.get_messages_for_channel_pair(SRC, DST_A) == []
        assert [m.mirror_id for m in await db.get_messages(3, SRC)] == [104]
    with_db(scenario)


def test_update_source_media_id_touches_one_row(with_db):
    async def scenario(db):
        await db.insert_batch([_mm(1, 11, media=1), _mm(1, 12, DST_B, media=1)])
        await db.update_source_media_id(SRC, 1, DST_A, 11, 99)
        assert {m.mirror_id: m.source_media_id for m in await db.get_messages(1, SRC)} \
            == {11: 99, 12: 1}
    with_db(scenario)


def test_checkpoint_and_drip_state(with_db):
    async def scenario(db):
        assert await db.get_past_mode_checkpoint(SRC, DST_A) is None
        assert await db.get_drip_state(SRC, DST_A) == (None, None)
        await db.set_past_mode_checkpoint(SRC, DST_A, 42)
        await db.set_past_mode_checkpoint(SRC, DST_A, 43)  # upsert
        await db.set_past_mode_checkpoint(SRC, DST_B, 7)
        await db.set_drip_sent(SRC, DST_A, 100.5)
        await db.set_drip_done(SRC, DST_A, "last_n=5")
        await db.set_drip_sent(SRC, DST_A, 200.25)  # keeps `done`
        await db.set_drip_done(SRC, DST_B, "all")  # alone: no sent time
        assert await db.get_past_mode_checkpoint(SRC, DST_A) == 43
        assert await db.get_drip_state(SRC, DST_A) == (200.25, "last_n=5")
        assert await db.get_drip_state(SRC, DST_B) == (None, "all")
        await db.delete_past_mode_checkpoint(SRC, DST_A)
        await db.delete_past_mode_checkpoint(SRC, DST_A)  # absent: no error
        assert await db.get_past_mode_checkpoint(SRC, DST_A) is None
        assert await db.get_drip_state(SRC, DST_A) == (None, None)
        assert await db.get_past_mode_checkpoint(SRC, DST_B) == 7
    with_db(scenario)


def test_broadcast_sync(with_db):
    async def scenario(db):
        assert await db.get_broadcast_sync(SRC) == {}
        await db.set_broadcast_sync(SRC, 1, None)
        await db.set_broadcast_sync(SRC, 2, 100)
        await db.set_broadcast_sync(SRC, 1, 150)  # upsert
        await db.set_broadcast_sync(SRC_B, 1, 5)
        assert await db.get_broadcast_sync(SRC) == {1: 150, 2: 100}
        await db.delete_broadcast_sync(SRC, [])
        await db.delete_broadcast_sync(SRC, [1, 999])
        assert await db.get_broadcast_sync(SRC) == {2: 100}
        assert await db.get_broadcast_sync(SRC_B) == {1: 5}
    with_db(scenario)


def test_fingerprints(with_db):
    async def scenario(db):
        await db.remember_fingerprint(DST_A, None, "fp", SRC, [1, 2], at=1000)  # an album
        await db.remember_fingerprint(DST_A, 7, "fp", SRC, [5], at=1000)
        # another post: a repeat; the same post again (a retry): not one
        assert await db.seen_fingerprint(DST_A, None, "fp", 900, SRC, [3])
        assert not await db.seen_fingerprint(DST_A, None, "fp", 900, SRC, [1, 2])
        assert await db.seen_fingerprint(DST_A, None, "fp", 900, SRC_B, [1])
        assert await db.seen_fingerprint(DST_A, None, "fp", 900, SRC, [])
        # older than the window, another topic, another fingerprint, another target
        assert not await db.seen_fingerprint(DST_A, None, "fp", 1001, SRC, [3])
        assert not await db.seen_fingerprint(DST_A, 8, "fp", 900, SRC, [3])
        assert not await db.seen_fingerprint(DST_A, None, "other", 900, SRC, [3])
        assert not await db.seen_fingerprint(DST_B, None, "fp", 900, SRC, [3])
        # forgotten only once every item of the album is
        await db.forget_fingerprints(DST_A, None, SRC, [1])
        assert await db.seen_fingerprint(DST_A, None, "fp", 900, SRC, [3])
        await db.forget_fingerprints(DST_A, None, SRC, [2])
        assert not await db.seen_fingerprint(DST_A, None, "fp", 900, SRC, [3])
        assert await db.seen_fingerprint(DST_A, 7, "fp", 900, SRC, [3])  # topic 7 kept
    with_db(scenario)


def test_prune_fingerprints_keeps_another_projects(with_db):
    async def scenario(db):
        await db.remember_fingerprint(DST_A, None, "old", SRC, [1], at=100)
        await db.remember_fingerprint(DST_A, None, "new", SRC, [2], at=1000)
        await db.remember_fingerprint(DST_A, None, "theirs", SRC_B, [3], at=100)
        await db.remember_fingerprint(DST_B, None, "theirs", SRC, [4], at=100)
        await db.prune_fingerprints(500, [SRC], [DST_A])
        assert not await db.seen_fingerprint(DST_A, None, "old", 0, SRC, [9])
        assert await db.seen_fingerprint(DST_A, None, "new", 0, SRC, [9])
        assert await db.seen_fingerprint(DST_A, None, "theirs", 0, SRC, [9])
        assert await db.seen_fingerprint(DST_B, None, "theirs", 0, SRC, [9])
    with_db(scenario)


# --- Postgres only: the schema and the pool --------------------------------


def _tables_and_columns(dsn):
    with psycopg.connect(dsn) as conn:
        columns = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = 'binding_id'"
        ).fetchall()
        indexes = conn.execute(
            "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema()"
        ).fetchall()
    return {c for (c,) in columns}, {i for (i,) in indexes}


def test_schema_is_created_and_a_second_start_keeps_it(dsn):
    async def start_twice():
        for _ in range(2):
            db = await PostgresDatabase(dsn)
            await db.insert_batch([_mm(1, 11)])
            await db.close()
    run(start_twice())
    columns, indexes = _tables_and_columns(dsn)
    assert {"mirror_topic_id", "source_topic_id", "source_media_id"} <= columns
    assert {"binding_id_original_idx", "binding_id_channel_pair_idx",
            "post_fingerprint_lookup_idx", "post_fingerprint_created_idx"} <= indexes


def test_an_old_binding_id_gets_its_new_columns(dsn):
    with psycopg.connect(dsn) as conn:
        conn.execute(
            "CREATE TABLE binding_id (id serial primary key not null, "
            "original_id bigint not null, original_channel bigint not null, "
            "mirror_id bigint not null, mirror_channel bigint not null)"
        )
        conn.execute("INSERT INTO binding_id (original_id, original_channel, mirror_id, "
                     "mirror_channel) VALUES (1, %s, 11, %s)", (SRC, DST_A))

    async def read():
        db = await PostgresDatabase(dsn)
        try:
            return await db.get_messages(1, SRC)
        finally:
            await db.close()
    assert run(read()) == [_mm(1, 11)]
    assert "binding_id_original_idx" in _tables_and_columns(dsn)[1]


def test_processes_starting_at_once_on_a_fresh_database(dsn):
    """Without the migration's advisory lock, concurrent CREATE TABLE IF NOT
    EXISTS can fail on pg_type's unique index."""
    async def start_together():
        dbs = await asyncio.gather(*(PostgresDatabase(dsn) for _ in range(6)))
        for db in dbs:
            await db.close()
    run(start_together())


def test_a_connection_the_server_dropped_is_replaced(dsn):
    """A Postgres restart kills the pool's idle connections: the next query
    must get a live one, not fail (an insert_batch of a post already sent)."""
    async def scenario():
        db = await PostgresDatabase(dsn)
        try:
            await db.insert_batch([_mm(1, 11)])
            with psycopg.connect(URL, autocommit=True) as conn:
                killed = conn.execute(
                    "SELECT pg_terminate_backend(pid, 5000) FROM pg_stat_activity "
                    "WHERE application_name = %s AND pid <> pg_backend_pid()", (APP,)
                ).fetchall()
            assert killed and all(ok for (ok,) in killed)
            await db.insert_batch([_mm(2, 22)])
            return sorted(m.mirror_id for m in await db.get_messages_batch([1, 2], SRC))
        finally:
            await db.close()
    assert run(scenario()) == [11, 22]
