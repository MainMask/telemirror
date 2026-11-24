import logging
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, NamedTuple, Optional, Tuple

from psycopg import AsyncCursor, errors
from psycopg.rows import class_row
from psycopg_pool import AsyncConnectionPool

from .misc.lrucache import LRUCache


class MirrorMessage(NamedTuple):
    """
    Mirror message class contains id message mappings:

    `original_message_id` <-> `mirror_message_id`

    Args:
        original_id (`int`): Original message ID
        original_channel (`int`): Source channel ID
        mirror_id (`int`): Mirror message ID
        mirror_channel (`int`): Mirror channel ID
        mirror_topic_id (`int`, optional): Forum topic this mirror was posted
            into (the `DirectionConfig.to_topic_id` that produced it), or
            `None` for a non-topic-scoped mirror. Lets a channel reached by
            more than one topic-scoped direction be disambiguated instead of
            treated as one ambiguous blob.
        source_topic_id (`int`, optional): The `DirectionConfig.from_topic_id`
            that produced this mirror (the config's own declared value, not
            necessarily the source message's actual topic). Needed alongside
            `mirror_topic_id` because two directions can share the same
            destination topic (e.g. both `to_topic_id=None` for a non-forum
            target) while differing in `from_topic_id` — `mirror_topic_id`
            alone can't tell such rows apart.
        source_media_id (`int`, optional): Id of the source photo/document
            this mirror was produced from (`source_media_id` in
            messagefilters/_media.py), or `None` (no such media, or a row
            written before this column existed). Lets `edit_message` tell a
            caption-only edit (same media) from a real media replacement.
    """

    original_id: int
    original_channel: int
    mirror_id: int
    mirror_channel: int
    mirror_topic_id: Optional[int] = None
    source_topic_id: Optional[int] = None
    source_media_id: Optional[int] = None


class Database(ABC):
    """
    Base database class

    Where the mirror keeps what it has sent (``MirrorMessage`` rows), the
    history replay's checkpoints and the broadcast-sync state.
    """

    @abstractmethod
    async def _async__init__(self: "Database") -> "Database":
        """Async initializer"""
        raise NotImplementedError

    def __await__(self):
        return self._async__init__().__await__()


    @abstractmethod
    async def insert_batch(self: "Database", entity: List[MirrorMessage]) -> None:
        """Inserts `MirrorMessage` objects into database

        Args:
            entity (`List[MirrorMessage]`): List of `MirrorMessage` objects
        """
        raise NotImplementedError

    @abstractmethod
    async def get_messages(
        self: "Database", original_id: int, original_channel: int
    ) -> List[MirrorMessage]:
        """
        Finds `MirrorMessage` objects with `original_id` and `original_channel` values

        Args:
            original_id (`int`): Original message ID
            original_channel (`int`): Source channel ID

        Returns:
            List[MirrorMessage]
        """
        raise NotImplementedError

    @abstractmethod
    async def get_messages_batch(
        self: "Database", original_ids: List[int], original_channel: int
    ) -> List[MirrorMessage]:
        """
        Finds `MirrorMessage` objects with `original_id` and `original_channel` values

        Args:
            original_ids (`List[int]`): Original message IDs
            original_channel (`int`): Source channel ID

        Returns:
            List[MirrorMessage]
        """
        raise NotImplementedError

    @abstractmethod
    async def delete_messages_for_channels_batch(
        self: "Database",
        original_channel: int,
        mirror_ids_by_channel: Dict[int, List[int]],
    ) -> None:
        """
        Deletes `MirrorMessage` objects matching `original_channel`, scoped
        per mirror channel to the `mirror_id`s in `mirror_ids_by_channel`
        — precise row-level scoping, in one call covering every channel. A
        channel reached by more than one topic-scoped direction can hold
        several rows sharing the same `original_id` (one per topic);
        scoping by `mirror_id` (unique per channel) instead of
        `original_id` means purging one topic's successfully-deleted row
        never also drops a sibling topic's still-live row for the same
        `original_id`/`mirror_channel`.

        Args:
            original_channel (`int`): Source channel ID
            mirror_ids_by_channel (`Dict[int, List[int]]`): Mirror message
                IDs to delete, keyed by mirror channel ID
        """
        raise NotImplementedError

    @abstractmethod
    async def get_messages_for_channel_pair(
        self: "Database", original_channel: int, mirror_channel: int
    ) -> List[MirrorMessage]:
        """Returns all `MirrorMessage` objects for a given source→mirror channel pair."""
        raise NotImplementedError

    @abstractmethod
    async def count_mirrored(
        self: "Database", original_channel: int, mirror_channel: int, up_to: int
    ) -> int:
        """How many source messages of the pair, ids ``up_to`` and below, have
        a mirror — counted once each, however many rows (topics) they have;
        without loading the rows."""
        raise NotImplementedError

    @abstractmethod
    async def update_source_media_id(
        self: "Database",
        original_channel: int,
        original_id: int,
        mirror_channel: int,
        mirror_id: int,
        media_id: int,
    ) -> None:
        """Records the source media a mirror now carries, after `edit_message`
        replaced it. Scoped by the source ids too, so Postgres can use the
        `(original_channel, original_id)` index."""
        raise NotImplementedError

    @abstractmethod
    async def get_past_mode_checkpoint(
        self: "Database", source: int, target: int
    ) -> Optional[int]:
        """Returns last processed message_id for source→target pair, or None"""
        raise NotImplementedError

    @abstractmethod
    async def set_past_mode_checkpoint(
        self: "Database", source: int, target: int, message_id: int
    ) -> None:
        """Upserts checkpoint for source→target pair"""
        raise NotImplementedError

    @abstractmethod
    async def delete_past_mode_checkpoint(
        self: "Database", source: int, target: int
    ) -> None:
        """Removes the checkpoint for a source→target pair (no-op if absent).

        Used by the ``clear_channels`` maintenance script after a target is wiped.
        The pair's drip state (`get_drip_state`) goes with it: the history is
        copied again.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_drip_state(
        self: "Database", source: int, target: int
    ) -> Tuple[Optional[float], Optional[str]]:
        """A drip's (``past_mode.drip``) state for a source→target pair:
        (when it last sent a post — unix time, the history it finished — its
        strategy), each None when not yet."""
        raise NotImplementedError

    @abstractmethod
    async def set_drip_sent(self: "Database", source: int, target: int, at: float) -> None:
        """Upserts when the pair's drip last sent a post (unix time)."""
        raise NotImplementedError

    @abstractmethod
    async def set_drip_done(self: "Database", source: int, target: int, done: str) -> None:
        """Upserts the history (its strategy) the pair's drip has finished."""
        raise NotImplementedError

    @abstractmethod
    async def delete_bindings_for_mirror(
        self: "Database", mirror_channel: int
    ) -> None:
        """Removes every message mapping whose ``mirror_channel`` matches.

        Used by the ``clear_channels`` maintenance script after a target is wiped.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_broadcast_sync(self: "Database", source: int) -> Dict[int, Optional[int]]:
        """Returns {message_id: synced_edit_ts} for every message of `source`
        already handled by the startup broadcast sync (`synced_edit_ts` is the
        unix timestamp of the last synced `edit_date`, or None if never edited)."""
        raise NotImplementedError

    @abstractmethod
    async def set_broadcast_sync(
        self: "Database", source: int, message_id: int, edit_ts: Optional[int]
    ) -> None:
        """Upserts the broadcast-sync state for one source message."""
        raise NotImplementedError

    @abstractmethod
    async def delete_broadcast_sync(
        self: "Database", source: int, message_ids: List[int]
    ) -> None:
        """Removes broadcast-sync rows for messages deleted from the source."""
        raise NotImplementedError

    @abstractmethod
    async def seen_fingerprint(
        self: "Database", target: int, topic: Optional[int], fingerprint: str, since: int,
        original_channel: int, original_ids: List[int],
    ) -> bool:
        """True when `target` (`topic`) got a post with this fingerprint at or
        after `since` (unix time) from another source post than this one (its
        ids: an album's items) — a repeat (``dedup_hours``). The same post
        again (a retry, another topic) isn't one."""
        raise NotImplementedError

    @abstractmethod
    async def remember_fingerprint(
        self: "Database", target: int, topic: Optional[int], fingerprint: str,
        original_channel: int, original_ids: List[int], at: int,
    ) -> None:
        """`target` (`topic`) got this post at `at` (unix time) — under each of
        its ids (an album's items): it's forgotten only once every one is
        (`forget_fingerprints`), the whole copy deleted."""
        raise NotImplementedError

    @abstractmethod
    async def prune_fingerprints(
        self: "Database", before: int, sources: List[int], targets: List[int]
    ) -> None:
        """Forgets the fingerprints remembered before `before` (unix time) of
        posts from `sources` to `targets` — only the caller's own: the database
        is shared by every project, and another one may keep its longer."""
        raise NotImplementedError

    @abstractmethod
    async def forget_fingerprints(
        self: "Database", target: int, topic: Optional[int], original_channel: int,
        original_ids: List[int],
    ) -> None:
        """Forgets what `target` (`topic`) got from these source posts: their
        copies there are deleted — no reason any more to skip the same post."""
        raise NotImplementedError

    async def close(self: "Database") -> None:  # noqa: B027 - intentional no-op default
        """Release any held resources (connection pool). No-op by default."""

    def __repr__(self) -> str:
        return self.__class__.__name__


async def open_database(db_url: Optional[str], logger: logging.Logger) -> "Database":
    """The configured database, opened: Postgres at ``db_url`` (the config's
    ``DB_URL``), else — ``USE_MEMORY_DB`` — an InMemoryDatabase, with a
    warning about its process-wide capacity."""
    if db_url is not None:
        return await PostgresDatabase(connection_string=db_url)
    logger.warning(
        f"USE_MEMORY_DB=true: InMemoryDatabase holds at most "
        f"{InMemoryDatabase.MAX_CAPACITY} tracked messages for the WHOLE "
        "PROCESS (not per channel). Once that's exceeded, LRU eviction can "
        "silently break dedup, delete, and edit-reply lookups for older "
        "messages — not just broadcast-channel resync on restart. Use "
        "PostgreSQL for a 24/7 deployment."
    )
    return await InMemoryDatabase()


class InMemoryDatabase(Database):
    """
    In-memory database: process-lifetime, bounded (``MAX_CAPACITY`` source
    messages, and as many broadcast-sync entries per source) — for tests and
    short manual runs.
    """

    MAX_CAPACITY = 100

    def __init__(
        self: "InMemoryDatabase", max_capacity: int = MAX_CAPACITY
    ) -> None:
        self.__storage = LRUCache[str, List[MirrorMessage]](capacity=max_capacity)
        self.__checkpoints: Dict[Tuple[int, int], int] = {}
        self.__drips: Dict[Tuple[int, int], Tuple[Optional[float], Optional[str]]] = {}
        self.__capacity = max_capacity
        self.__broadcast_sync: Dict[int, LRUCache[int, Optional[int]]] = {}
        # (target, topic, fingerprint) → [(original_channel, original_id, at)]
        self.__fingerprints: Dict[Tuple[int, Optional[int], str], List[Tuple[int, int, int]]] = {}

    async def _async__init__(self: "InMemoryDatabase") -> "InMemoryDatabase":
        return self


    async def insert_batch(
        self: "InMemoryDatabase", entity: List[MirrorMessage]
    ) -> None:
        """Inserts `MirrorMessage` objects into database

        Args:
            entity (`List[MirrorMessage]`): List of `MirrorMessage` objects
        """
        for e in entity:
            self.__storage.setdefault(
                self.__build_message_key(e.original_id, e.original_channel), []
            ).append(e)

    async def get_messages(
        self: "InMemoryDatabase", original_id: int, original_channel: int
    ) -> List[MirrorMessage]:
        """
        Finds `MirrorMessage` objects with `original_id` and `original_channel` values

        Args:
            original_id (`int`): Original message ID
            original_channel (`int`): Source channel ID

        Returns:
            List[MirrorMessage]
        """
        # a copy: a caller's change must not reach the stored list
        return list(self.__storage.get(
            self.__build_message_key(original_id, original_channel), []
        ))

    async def get_messages_batch(
        self: "InMemoryDatabase", original_ids: List[int], original_channel: int
    ) -> List[MirrorMessage]:
        """
        Finds `MirrorMessage` objects with `original_id` and `original_channel` values

        Args:
            original_ids (`List[int]`): Original message IDs
            original_channel (`int`): Source channel ID

        Returns:
            List[MirrorMessage]
        """
        return [
            msg
            for idx in original_ids
            for msg in self.__storage.get(
                self.__build_message_key(idx, original_channel), []
            )
        ]

    async def delete_messages_for_channels_batch(
        self: "InMemoryDatabase",
        original_channel: int,
        mirror_ids_by_channel: Dict[int, List[int]],
    ) -> None:
        mirror_id_sets = {
            channel: set(ids) for channel, ids in mirror_ids_by_channel.items()
        }
        prefix = f"{original_channel}:"
        for key in list(self.__storage.keys()):
            if not key.startswith(prefix):
                continue
            kept = [
                m for m in self.__storage[key]
                if m.mirror_id not in mirror_id_sets.get(m.mirror_channel, ())
            ]
            if kept:
                self.__storage[key] = kept
            else:
                self.__storage.pop(key, None)

    async def get_messages_for_channel_pair(
        self: "InMemoryDatabase", original_channel: int, mirror_channel: int
    ) -> List[MirrorMessage]:
        prefix = f"{original_channel}:"
        return [
            m
            for key, msgs in self.__storage.items()
            if key.startswith(prefix)
            for m in msgs
            if m.mirror_channel == mirror_channel
        ]

    async def count_mirrored(
        self: "InMemoryDatabase", original_channel: int, mirror_channel: int, up_to: int
    ) -> int:
        return len({m.original_id for m in await self.get_messages_for_channel_pair(
            original_channel, mirror_channel) if m.original_id <= up_to})

    async def update_source_media_id(
        self: "InMemoryDatabase",
        original_channel: int,
        original_id: int,
        mirror_channel: int,
        mirror_id: int,
        media_id: int,
    ) -> None:
        msgs = self.__storage.get(
            self.__build_message_key(original_id, original_channel), []
        )
        for i, m in enumerate(msgs):
            if m.mirror_channel == mirror_channel and m.mirror_id == mirror_id:
                msgs[i] = m._replace(source_media_id=media_id)

    async def get_past_mode_checkpoint(
        self: "InMemoryDatabase", source: int, target: int
    ) -> Optional[int]:
        return self.__checkpoints.get((source, target))

    async def set_past_mode_checkpoint(
        self: "InMemoryDatabase", source: int, target: int, message_id: int
    ) -> None:
        self.__checkpoints[(source, target)] = message_id

    async def delete_past_mode_checkpoint(
        self: "InMemoryDatabase", source: int, target: int
    ) -> None:
        self.__checkpoints.pop((source, target), None)
        self.__drips.pop((source, target), None)

    async def get_drip_state(
        self: "InMemoryDatabase", source: int, target: int
    ) -> Tuple[Optional[float], Optional[str]]:
        return self.__drips.get((source, target), (None, None))

    async def set_drip_sent(self: "InMemoryDatabase", source: int, target: int, at: float) -> None:
        self.__drips[(source, target)] = (at, self.__drips.get((source, target), (None, None))[1])

    async def set_drip_done(self: "InMemoryDatabase", source: int, target: int, done: str) -> None:
        self.__drips[(source, target)] = (self.__drips.get((source, target), (None, None))[0], done)

    async def delete_bindings_for_mirror(
        self: "InMemoryDatabase", mirror_channel: int
    ) -> None:
        for key in list(self.__storage.keys()):
            kept = [
                m for m in self.__storage[key] if m.mirror_channel != mirror_channel
            ]
            if kept:
                self.__storage[key] = kept
            else:
                self.__storage.pop(key, None)

    async def get_broadcast_sync(
        self: "InMemoryDatabase", source: int
    ) -> Dict[int, Optional[int]]:
        return dict(self.__broadcast_sync.get(source, {}))

    async def set_broadcast_sync(
        self: "InMemoryDatabase", source: int, message_id: int, edit_ts: Optional[int]
    ) -> None:
        self.__broadcast_sync.setdefault(
            source, LRUCache[int, Optional[int]](capacity=self.__capacity)
        )[message_id] = edit_ts

    async def delete_broadcast_sync(
        self: "InMemoryDatabase", source: int, message_ids: List[int]
    ) -> None:
        bucket = self.__broadcast_sync.get(source)
        if bucket:
            for mid in message_ids:
                bucket.pop(mid, None)

    async def seen_fingerprint(
        self: "InMemoryDatabase", target: int, topic: Optional[int], fingerprint: str, since: int,
        original_channel: int, original_ids: List[int],
    ) -> bool:
        return any(
            at >= since and not (channel == original_channel and mid in original_ids)
            for channel, mid, at in self.__fingerprints.get((target, topic, fingerprint), [])
        )

    async def remember_fingerprint(
        self: "InMemoryDatabase", target: int, topic: Optional[int], fingerprint: str,
        original_channel: int, original_ids: List[int], at: int,
    ) -> None:
        self.__fingerprints.setdefault((target, topic, fingerprint), []).extend(
            (original_channel, original_id, at) for original_id in original_ids
        )

    async def prune_fingerprints(
        self: "InMemoryDatabase", before: int, sources: List[int], targets: List[int]
    ) -> None:
        for key in [k for k in self.__fingerprints if k[0] in targets]:
            kept = [row for row in self.__fingerprints[key] if row[2] >= before or row[0] not in sources]
            if kept:
                self.__fingerprints[key] = kept
            else:
                del self.__fingerprints[key]

    async def forget_fingerprints(
        self: "InMemoryDatabase", target: int, topic: Optional[int], original_channel: int,
        original_ids: List[int],
    ) -> None:
        for key in [k for k in self.__fingerprints if k[:2] == (target, topic)]:
            kept = [row for row in self.__fingerprints[key]
                    if row[0] != original_channel or row[1] not in original_ids]
            if kept:
                self.__fingerprints[key] = kept
            else:
                del self.__fingerprints[key]

    def __build_message_key(
        self: "InMemoryDatabase", original_id: int, original_channel: int
    ) -> str:
        """
        Builds message key from `original_id` and `original_channel` values

        Args:
            original_id (`int`): Original message ID
            original_channel (`int`): Source channel ID

        Returns:
            str
        """
        return f"{original_channel}:{original_id}"


class PostgresDatabase(Database):
    """
    Postgres database messages mapping implementation.

    Binding database table:

    ```
    create table binding_id (id serial primary key not null,
                original_id bigint not null,
                original_channel bigint not null,
                mirror_id bigint not null,
                mirror_channel bigint not null,
                mirror_topic_id bigint,
                source_topic_id bigint,
                source_media_id bigint)
    ```

    Args:
        connection_string (`str`): Postgres connection URL
    """

    MIN_CONN = 1
    # Per process — each project's mirror, a history replay, a task has its
    # own pool, all against one server (max_connections, 100 by default);
    # the queries are short, a few at once are plenty.
    MAX_CONN = 5
    # pg_advisory_xact_lock key the schema migration is serialized on
    SCHEMA_LOCK_KEY = 0x7E1E_0001

    def __init__(self, connection_string: str) -> None:
        self.__conn_info = connection_string

    async def _async__init__(self: "PostgresDatabase") -> "PostgresDatabase":
        self.connection_pool = AsyncConnectionPool(
            conninfo=self.__conn_info,
            min_size=self.MIN_CONN,
            max_size=self.MAX_CONN,
            open=False,
            # a connection the server dropped (a restart) is replaced before
            # use: otherwise the query it gets — an insert_batch of a post
            # already sent — fails, and the copy is never tracked
            check=AsyncConnectionPool.check_connection,
        )
        await self.connection_pool.open()
        try:
            await self.__create_tables_if_not_exists()
        except BaseException:
            # the caller gets no database to close: the pool (its
            # connections, its workers) would be left open
            await self.connection_pool.close()
            raise
        return self

    async def insert_batch(
        self: "PostgresDatabase", entity: List[MirrorMessage]
    ) -> None:
        """Inserts `MirrorMessage` objects into database

        Args:
            entity (`List[MirrorMessage]`): List of `MirrorMessage` objects
        """
        async with self.__pg_cursor() as cursor:
            await cursor.executemany(
                """
                INSERT INTO binding_id
                (original_id, original_channel, mirror_id, mirror_channel, mirror_topic_id, source_topic_id, source_media_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                entity,
            )

    async def get_messages(
        self: "PostgresDatabase", original_id: int, original_channel: int
    ) -> List[MirrorMessage]:
        """
        Finds `MirrorMessage` objects with `original_id` and `original_channel` values

        Args:
            original_id (`int`): Original message ID
            original_channel (`int`): Source channel ID

        Returns:
            List[MirrorMessage]
        """
        async with self.__pg_cursor() as cursor:
            cursor.row_factory = class_row(MirrorMessage)
            await cursor.execute(
                """
                SELECT original_id, original_channel, mirror_id, mirror_channel, mirror_topic_id, source_topic_id, source_media_id
                FROM binding_id
                WHERE original_channel = %s
                AND original_id = %s
                """,
                (
                    original_channel,
                    original_id,
                ),
            )
            rows = await cursor.fetchall()
        return rows

    async def get_messages_batch(
        self: "PostgresDatabase", original_ids: List[int], original_channel: int
    ) -> List[MirrorMessage]:
        """
        Finds `MirrorMessage` objects with `original_id` and `original_channel` values

        Args:
            original_ids (`List[int]`): Original message IDs
            original_channel (`int`): Source channel ID

        Returns:
            List[MirrorMessage]
        """
        async with self.__pg_cursor() as cursor:
            cursor.row_factory = class_row(MirrorMessage)
            await cursor.execute(
                """
                SELECT original_id, original_channel, mirror_id, mirror_channel, mirror_topic_id, source_topic_id, source_media_id
                FROM binding_id
                WHERE original_channel = %s
                AND original_id = ANY(%s)
                """,
                (
                    original_channel,
                    original_ids,
                ),
            )
            rows = await cursor.fetchall()
        return rows

    async def delete_messages_for_channels_batch(
        self: "PostgresDatabase",
        original_channel: int,
        mirror_ids_by_channel: Dict[int, List[int]],
    ) -> None:
        """
        Deletes `MirrorMessage` objects matching `original_channel`, scoped
        per mirror channel to the `mirror_id`s in `mirror_ids_by_channel`,
        in a single statement covering every channel.

        Args:
            original_channel (`int`): Source channel ID
            mirror_ids_by_channel (`Dict[int, List[int]]`): Mirror message
                IDs to delete, keyed by mirror channel ID
        """
        if not mirror_ids_by_channel:
            return
        channels = []
        ids = []
        for channel, mirror_ids in mirror_ids_by_channel.items():
            for mirror_id in mirror_ids:
                channels.append(channel)
                ids.append(mirror_id)
        async with self.__pg_cursor() as cursor:
            await cursor.execute(
                """
                DELETE FROM binding_id
                WHERE original_channel = %s
                AND (mirror_channel, mirror_id) IN (
                    SELECT * FROM unnest(%s::bigint[], %s::bigint[])
                )
                """,
                (
                    original_channel,
                    channels,
                    ids,
                ),
            )

    async def get_messages_for_channel_pair(
        self: "PostgresDatabase", original_channel: int, mirror_channel: int
    ) -> List[MirrorMessage]:
        async with self.__pg_cursor() as cursor:
            cursor.row_factory = class_row(MirrorMessage)
            await cursor.execute(
                "SELECT original_id, original_channel, mirror_id, mirror_channel, mirror_topic_id, source_topic_id, source_media_id "
                "FROM binding_id "
                "WHERE original_channel = %s AND mirror_channel = %s",
                (original_channel, mirror_channel),
            )
            return await cursor.fetchall()

    async def count_mirrored(
        self: "PostgresDatabase", original_channel: int, mirror_channel: int, up_to: int
    ) -> int:
        async with self.__pg_cursor() as cursor:
            await cursor.execute(
                "SELECT count(DISTINCT original_id) FROM binding_id "
                "WHERE original_channel = %s AND mirror_channel = %s AND original_id <= %s",
                (original_channel, mirror_channel, up_to),
            )
            row = await cursor.fetchone()
        return row[0] if row else 0

    async def update_source_media_id(
        self: "PostgresDatabase",
        original_channel: int,
        original_id: int,
        mirror_channel: int,
        mirror_id: int,
        media_id: int,
    ) -> None:
        async with self.__pg_cursor() as cursor:
            await cursor.execute(
                "UPDATE binding_id SET source_media_id = %s "
                "WHERE original_channel = %s AND original_id = %s "
                "AND mirror_channel = %s AND mirror_id = %s",
                (media_id, original_channel, original_id, mirror_channel, mirror_id),
            )

    async def __create_tables_if_not_exists(self: "PostgresDatabase"):
        """Create tables if not exists.

        Run by every process at its start, in one transaction: an advisory lock
        keeps two starting at once (a fresh database) from racing on the same
        CREATE TABLE. A column or an index is added only when it's missing —
        ALTER TABLE / CREATE INDEX lock the table even with IF NOT EXISTS, and
        the running mirrors would wait on each start's migration."""
        async with self.__pg_cursor() as cursor:
            await cursor.execute("SELECT pg_advisory_xact_lock(%s)", (self.SCHEMA_LOCK_KEY,))
            await cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS binding_id(
                    id serial primary key not null,
                    original_id bigint not null,
                    original_channel bigint not null,
                    mirror_id bigint not null,
                    mirror_channel bigint not null,
                    mirror_topic_id bigint,
                    source_topic_id bigint,
                    source_media_id bigint
                );

                CREATE TABLE IF NOT EXISTS past_mode_checkpoint (
                    source_channel BIGINT NOT NULL,
                    target_channel BIGINT NOT NULL,
                    last_message_id BIGINT NOT NULL,
                    PRIMARY KEY (source_channel, target_channel)
                );

                CREATE TABLE IF NOT EXISTS past_mode_drip (
                    source_channel BIGINT NOT NULL,
                    target_channel BIGINT NOT NULL,
                    last_sent_at   DOUBLE PRECISION,
                    done           TEXT,
                    PRIMARY KEY (source_channel, target_channel)
                );

                CREATE TABLE IF NOT EXISTS broadcast_sync (
                    source_channel BIGINT NOT NULL,
                    message_id     BIGINT NOT NULL,
                    synced_edit_ts BIGINT,
                    PRIMARY KEY (source_channel, message_id)
                );

                CREATE TABLE IF NOT EXISTS post_fingerprint (
                    target_channel   BIGINT NOT NULL,
                    target_topic     BIGINT,
                    fingerprint      TEXT   NOT NULL,
                    original_channel BIGINT NOT NULL,
                    original_id      BIGINT NOT NULL,
                    created_at       BIGINT NOT NULL
                );
                """
            )
            # binding_id created before these columns existed
            await cursor.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = 'binding_id'"
            )
            columns = {row[0] for row in await cursor.fetchall()}
            for column in ("mirror_topic_id", "source_topic_id", "source_media_id"):
                if column not in columns:
                    await cursor.execute(f"ALTER TABLE binding_id ADD COLUMN {column} bigint")
            for name, on in (
                ("binding_id_original_idx", "binding_id (original_channel, original_id)"),
                ("binding_id_channel_pair_idx", "binding_id (original_channel, mirror_channel)"),
                ("post_fingerprint_lookup_idx", "post_fingerprint (target_channel, fingerprint)"),
                ("post_fingerprint_created_idx", "post_fingerprint (created_at)"),
            ):
                await cursor.execute("SELECT to_regclass(%s)", (name,))
                row = await cursor.fetchone()
                if row is None or row[0] is None:
                    await cursor.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {on}")

    async def get_past_mode_checkpoint(
        self: "PostgresDatabase", source: int, target: int
    ) -> Optional[int]:
        async with self.__pg_cursor() as cursor:
            await cursor.execute(
                "SELECT last_message_id FROM past_mode_checkpoint "
                "WHERE source_channel = %s AND target_channel = %s",
                (source, target),
            )
            row = await cursor.fetchone()
        return row[0] if row else None

    async def set_past_mode_checkpoint(
        self: "PostgresDatabase", source: int, target: int, message_id: int
    ) -> None:
        async with self.__pg_cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO past_mode_checkpoint (source_channel, target_channel, last_message_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (source_channel, target_channel)
                DO UPDATE SET last_message_id = EXCLUDED.last_message_id
                """,
                (source, target, message_id),
            )

    async def delete_past_mode_checkpoint(
        self: "PostgresDatabase", source: int, target: int
    ) -> None:
        async with self.__pg_cursor() as cursor:
            await cursor.execute(
                "DELETE FROM past_mode_checkpoint "
                "WHERE source_channel = %s AND target_channel = %s",
                (source, target),
            )
            await cursor.execute(
                "DELETE FROM past_mode_drip "
                "WHERE source_channel = %s AND target_channel = %s",
                (source, target),
            )

    async def get_drip_state(
        self: "PostgresDatabase", source: int, target: int
    ) -> Tuple[Optional[float], Optional[str]]:
        async with self.__pg_cursor() as cursor:
            await cursor.execute(
                "SELECT last_sent_at, done FROM past_mode_drip "
                "WHERE source_channel = %s AND target_channel = %s",
                (source, target),
            )
            row = await cursor.fetchone()
        return (row[0], row[1]) if row else (None, None)

    async def set_drip_sent(self: "PostgresDatabase", source: int, target: int, at: float) -> None:
        async with self.__pg_cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO past_mode_drip (source_channel, target_channel, last_sent_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (source_channel, target_channel)
                DO UPDATE SET last_sent_at = EXCLUDED.last_sent_at
                """,
                (source, target, at),
            )

    async def set_drip_done(self: "PostgresDatabase", source: int, target: int, done: str) -> None:
        async with self.__pg_cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO past_mode_drip (source_channel, target_channel, done)
                VALUES (%s, %s, %s)
                ON CONFLICT (source_channel, target_channel)
                DO UPDATE SET done = EXCLUDED.done
                """,
                (source, target, done),
            )

    async def delete_bindings_for_mirror(
        self: "PostgresDatabase", mirror_channel: int
    ) -> None:
        async with self.__pg_cursor() as cursor:
            await cursor.execute(
                "DELETE FROM binding_id WHERE mirror_channel = %s",
                (mirror_channel,),
            )

    async def get_broadcast_sync(
        self: "PostgresDatabase", source: int
    ) -> Dict[int, Optional[int]]:
        async with self.__pg_cursor() as cursor:
            await cursor.execute(
                "SELECT message_id, synced_edit_ts FROM broadcast_sync "
                "WHERE source_channel = %s",
                (source,),
            )
            rows = await cursor.fetchall()
        return dict(rows)

    async def set_broadcast_sync(
        self: "PostgresDatabase", source: int, message_id: int, edit_ts: Optional[int]
    ) -> None:
        async with self.__pg_cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO broadcast_sync (source_channel, message_id, synced_edit_ts)
                VALUES (%s, %s, %s)
                ON CONFLICT (source_channel, message_id)
                DO UPDATE SET synced_edit_ts = EXCLUDED.synced_edit_ts
                """,
                (source, message_id, edit_ts),
            )

    async def seen_fingerprint(
        self: "PostgresDatabase", target: int, topic: Optional[int], fingerprint: str, since: int,
        original_channel: int, original_ids: List[int],
    ) -> bool:
        async with self.__pg_cursor() as cursor:
            await cursor.execute(
                "SELECT 1 FROM post_fingerprint "
                "WHERE target_channel = %s AND target_topic IS NOT DISTINCT FROM %s "
                "AND fingerprint = %s AND created_at >= %s "
                "AND NOT (original_channel = %s AND original_id = ANY(%s)) LIMIT 1",
                (target, topic, fingerprint, since, original_channel, original_ids),
            )
            return await cursor.fetchone() is not None

    async def remember_fingerprint(
        self: "PostgresDatabase", target: int, topic: Optional[int], fingerprint: str,
        original_channel: int, original_ids: List[int], at: int,
    ) -> None:
        async with self.__pg_cursor() as cursor:
            await cursor.executemany(
                "INSERT INTO post_fingerprint (target_channel, target_topic, fingerprint, "
                "original_channel, original_id, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
                [(target, topic, fingerprint, original_channel, original_id, at)
                 for original_id in original_ids],
            )

    async def prune_fingerprints(
        self: "PostgresDatabase", before: int, sources: List[int], targets: List[int]
    ) -> None:
        async with self.__pg_cursor() as cursor:
            await cursor.execute(
                "DELETE FROM post_fingerprint WHERE created_at < %s "
                "AND original_channel = ANY(%s) AND target_channel = ANY(%s)",
                (before, sources, targets),
            )

    async def forget_fingerprints(
        self: "PostgresDatabase", target: int, topic: Optional[int], original_channel: int,
        original_ids: List[int],
    ) -> None:
        async with self.__pg_cursor() as cursor:
            await cursor.execute(
                "DELETE FROM post_fingerprint "
                "WHERE target_channel = %s AND target_topic IS NOT DISTINCT FROM %s "
                "AND original_channel = %s AND original_id = ANY(%s)",
                (target, topic, original_channel, original_ids),
            )

    async def delete_broadcast_sync(
        self: "PostgresDatabase", source: int, message_ids: List[int]
    ) -> None:
        if not message_ids:
            return
        async with self.__pg_cursor() as cursor:
            await cursor.execute(
                "DELETE FROM broadcast_sync "
                "WHERE source_channel = %s AND message_id = ANY(%s)",
                (source, message_ids),
            )

    async def close(self: "PostgresDatabase") -> None:
        """Close the connection pool."""
        await self.connection_pool.close()

    @asynccontextmanager
    async def __pg_cursor(self: "PostgresDatabase") -> AsyncIterator[AsyncCursor[Any]]:
        """
        Gets connection from pool and yields cursor within current context

        Yields:
            (`psycopg.AsyncCursor`): Cursor
        """
        async with self.connection_pool.connection() as con:
            try:
                async with con.cursor() as cur:
                    yield cur
            except errors.OperationalError:
                # If we get an operational error check the pool
                await self.connection_pool.check()
                raise
            except errors.DatabaseError:
                if con is not None:
                    await con.rollback()
                raise
