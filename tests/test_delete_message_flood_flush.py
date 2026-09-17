"""delete_message's DB purge is scoped per mirror_channel:
`delete_messages_for_channels_batch` purges a message's row for exactly the
channel(s) whose Telegram delete just succeeded, independent of any sibling
channel's outcome. So after a FloodWait (or any other failure) on one
channel:

- a channel whose Telegram delete succeeded has its rows purged immediately,
  even if a sibling channel for the same original_id failed/was
  unconfigured/was never attempted, but
- a channel that failed, was never attempted (no direction config), or is
  configured with disable_delete=True keeps its row — that would silently
  drop DB tracking for a mirror message still sitting on Telegram, with no
  way to retry deleting it later.

delete_message itself must not raise on a flood (see
test_edit_delete_flood_propagates.py for why) — every channel is always
attempted regardless of an earlier one's failure."""

import logging

from telethon import errors

from config import DirectionConfig
from telemirror.messagefilters import EmptyMessageFilter
from telemirror.mirroring import EventProcessor
from telemirror.storage import InMemoryDatabase, MirrorMessage
from tests.conftest import run

SOURCE = -1001111111111
TARGET_A = -1002222222222
TARGET_B = -1003333333333


def _direction():
    return DirectionConfig(
        disable_delete=False, disable_edit=False, filters=EmptyMessageFilter()
    )


class _PartialFloodClient:
    """TARGET_A's delete succeeds; TARGET_B's floods."""

    def __init__(self):
        self.deleted: list[int] = []

    async def delete_messages(self, entity, message_ids):
        if entity == TARGET_A:
            self.deleted.append(entity)
            return
        raise errors.FloodWaitError(request=None)


def test_fully_completed_message_is_purged_even_when_another_channel_floods():
    """original_id 100 lives only in TARGET_A (successfully deleted); 200 lives
    only in TARGET_B (floods) — 100 must be purged, 200 must not."""
    db = run(InMemoryDatabase())
    run(db.insert(MirrorMessage(100, SOURCE, 5000, TARGET_A)))
    run(db.insert(MirrorMessage(200, SOURCE, 9000, TARGET_B)))

    client = _PartialFloodClient()
    proc = EventProcessor(
        chat_mapping={SOURCE: {TARGET_A: [_direction()], TARGET_B: [_direction()]}},
        database=db,
        client=client,
        logger=logging.getLogger("test.deleteflush"),
    )

    run(proc.delete_message(SOURCE, [100, 200]))  # must not raise

    assert client.deleted == [TARGET_A]
    assert run(db.get_messages(100, SOURCE)) == []
    assert len(run(db.get_messages(200, SOURCE))) == 1


def test_flooded_channels_row_survives_while_succeeded_channels_purge():
    """original_id 100 is mirrored into *both* TARGET_A and TARGET_B — TARGET_A's
    delete succeeds and its row is purged right away; TARGET_B's copy is still
    untouched on Telegram when the flood hits, so its DB row must survive for
    a future retry to find it."""
    db = run(InMemoryDatabase())
    run(db.insert(MirrorMessage(100, SOURCE, 5000, TARGET_A)))
    run(db.insert(MirrorMessage(100, SOURCE, 9000, TARGET_B)))

    client = _PartialFloodClient()
    proc = EventProcessor(
        chat_mapping={SOURCE: {TARGET_A: [_direction()], TARGET_B: [_direction()]}},
        database=db,
        client=client,
        logger=logging.getLogger("test.deleteflush"),
    )

    run(proc.delete_message(SOURCE, [100]))  # must not raise

    assert client.deleted == [TARGET_A]
    remaining = run(db.get_messages(100, SOURCE))
    # TARGET_A's row purged immediately; TARGET_B's mirror is still live on
    # Telegram, so its row must stay tracked.
    assert [m.mirror_channel for m in remaining] == [TARGET_B]


def test_channel_missing_from_chat_mapping_keeps_its_row_while_others_purge():
    """original_id 100 has a DB row in TARGET_B, but TARGET_B was removed from
    chat_mapping (e.g. the direction was deleted from config) — delete_message
    never attempts (and never can attempt) a Telegram delete there, so
    TARGET_B's row must survive even though TARGET_A's delete succeeds and is
    purged: TARGET_B's row is still the only record of that still-live
    mirror."""
    db = run(InMemoryDatabase())
    run(db.insert(MirrorMessage(100, SOURCE, 5000, TARGET_A)))
    run(db.insert(MirrorMessage(100, SOURCE, 9000, TARGET_B)))

    class _SucceedsClient:
        async def delete_messages(self, entity, message_ids):
            pass

    proc = EventProcessor(
        chat_mapping={SOURCE: {TARGET_A: [_direction()]}},  # TARGET_B not configured
        database=db,
        client=_SucceedsClient(),
        logger=logging.getLogger("test.deleteflush"),
    )

    run(proc.delete_message(SOURCE, [100]))  # must not raise

    remaining = run(db.get_messages(100, SOURCE))
    assert [m.mirror_channel for m in remaining] == [TARGET_B]


def test_disable_delete_channel_keeps_its_row_while_others_purge():
    """Same as above, but TARGET_B is configured with disable_delete=True — its
    mirror is intentionally kept forever, so its row must survive even though
    TARGET_A's delete succeeds and is purged."""
    db = run(InMemoryDatabase())
    run(db.insert(MirrorMessage(100, SOURCE, 5000, TARGET_A)))
    run(db.insert(MirrorMessage(100, SOURCE, 9000, TARGET_B)))

    class _SucceedsClient:
        async def delete_messages(self, entity, message_ids):
            pass

    proc = EventProcessor(
        chat_mapping={
            SOURCE: {
                TARGET_A: [_direction()],
                TARGET_B: [DirectionConfig(
                    disable_delete=True, disable_edit=False, filters=EmptyMessageFilter()
                )],
            }
        },
        database=db,
        client=_SucceedsClient(),
        logger=logging.getLogger("test.deleteflush"),
    )

    run(proc.delete_message(SOURCE, [100]))  # must not raise

    remaining = run(db.get_messages(100, SOURCE))
    assert [m.mirror_channel for m in remaining] == [TARGET_B]


class _FailingPurgeDB(InMemoryDatabase):
    async def delete_messages_for_channels_batch(
        self, original_channel, mirror_ids_by_channel
    ):
        raise RuntimeError("db unavailable")


def test_purge_db_failure_is_logged_and_does_not_raise():
    db = run(_FailingPurgeDB())
    run(db.insert(MirrorMessage(100, SOURCE, 5000, TARGET_A)))
    run(db.insert(MirrorMessage(200, SOURCE, 9000, TARGET_B)))

    client = _PartialFloodClient()
    proc = EventProcessor(
        chat_mapping={SOURCE: {TARGET_A: [_direction()], TARGET_B: [_direction()]}},
        database=db,
        client=client,
        logger=logging.getLogger("test.deleteflush"),
    )

    run(proc.delete_message(SOURCE, [100, 200]))  # must not raise


def test_delete_message_respects_the_specific_topics_disable_delete():
    """TARGET_A is reached by two topic-scoped directions: topic 1 is
    `disable_delete=True` (protected), topic 2 is not. A row belonging to
    topic 1 must never be deleted just because topic 2's config for the same
    channel happens to be unprotected — picking "any non-disabled config for
    the channel" (the pre-mirror_topic_id behavior) would wrongly delete
    it."""
    db = run(InMemoryDatabase())
    run(db.insert_batch([
        MirrorMessage(100, SOURCE, 5000, TARGET_A, mirror_topic_id=1),
        MirrorMessage(100, SOURCE, 5001, TARGET_A, mirror_topic_id=2),
    ]))

    class _SucceedsClient:
        def __init__(self):
            self.deleted_ids: list[int] = []

        async def delete_messages(self, entity, message_ids):
            self.deleted_ids.extend(message_ids)

    client = _SucceedsClient()
    proc = EventProcessor(
        chat_mapping={
            SOURCE: {
                TARGET_A: [
                    DirectionConfig(
                        disable_delete=True, disable_edit=False,
                        filters=EmptyMessageFilter(), to_topic_id=1,
                    ),
                    DirectionConfig(
                        disable_delete=False, disable_edit=False,
                        filters=EmptyMessageFilter(), to_topic_id=2,
                    ),
                ]
            }
        },
        database=db,
        client=client,
        logger=logging.getLogger("test.deleteflush"),
    )

    run(proc.delete_message(SOURCE, [100]))

    assert client.deleted_ids == [5001]  # only topic 2's (unprotected) mirror
    remaining = run(db.get_messages(100, SOURCE))
    assert [m.mirror_id for m in remaining] == [5000]  # topic 1's row survives
