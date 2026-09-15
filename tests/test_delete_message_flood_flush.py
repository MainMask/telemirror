"""delete_message's DB purge must be scoped correctly: `delete_messages_batch`
has no mirror_channel granularity — it drops an original_id's DB row across
*every* mirror channel at once. So after a FloodWait (or any other failure) on
one channel:

- an original_id whose *every* target channel already had its Telegram delete
  confirmed is safe to purge (otherwise it's stuck in the DB forever even
  though it's already gone from Telegram everywhere), but
- an original_id with a channel that failed or was never attempted must NOT
  be purged — that would silently drop DB tracking for a mirror message still
  sitting on Telegram, with no way to retry deleting it later.

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


def test_message_needing_the_flooded_channel_is_not_purged():
    """original_id 100 is mirrored into *both* TARGET_A and TARGET_B — TARGET_B's
    copy is still untouched on Telegram when the flood hits, so its DB row must
    survive for a future retry to find it."""
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
    # TARGET_B's mirror is still live on Telegram — the row must stay tracked.
    assert len(run(db.get_messages(100, SOURCE))) == 2


def test_message_needing_an_unconfigured_channel_is_not_purged():
    """original_id 100 has a DB row in TARGET_B, but TARGET_B was removed from
    chat_mapping (e.g. the direction was deleted from config) — delete_message
    never attempts (and never can attempt) a Telegram delete there, so 100 must
    not be purged just because TARGET_A's delete succeeds: TARGET_B's row is
    still the only record of that still-live mirror."""
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

    # The purge is all-or-nothing per original_id — since TARGET_B was never
    # attempted, neither row is purged (TARGET_A's included).
    assert len(run(db.get_messages(100, SOURCE))) == 2


def test_message_needing_a_disable_delete_channel_is_not_purged():
    """Same as above, but TARGET_B is configured with disable_delete=True — its
    mirror is intentionally kept forever, so 100 must not be purged either."""
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

    assert len(run(db.get_messages(100, SOURCE))) == 2  # all-or-nothing, see above


class _FailingPurgeDB(InMemoryDatabase):
    async def delete_messages_batch(self, original_ids, original_channel):
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
