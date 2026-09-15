"""edit_message/delete_message are only reachable from live event handlers
(on_edit_message/on_deleted_message) and from _sync_broadcast_channel's
catch-up loop — neither has a retry wrapper for a FloodWaitError, unlike
new_message/new_album which past_mode.py replays and retries. So a flood on
one target must be logged and NOT propagate: propagating would only abort
processing of every other, un-flooded target for the same edit/delete, with
no compensating benefit (nothing upstream would ever retry it anyway)."""

import logging

from telethon import errors

from config import DirectionConfig
from telemirror.messagefilters import EmptyMessageFilter
from telemirror.mirroring import EventProcessor
from telemirror.storage import InMemoryDatabase, MirrorMessage
from tests.conftest import make_message, run

SOURCE = -1001111111111
TARGET_A = -1002222222222
TARGET_B = -1003333333333


def _direction():
    return DirectionConfig(
        disable_delete=False, disable_edit=False, filters=EmptyMessageFilter()
    )


class _FloodOnAEditClient:
    def __init__(self):
        self.edited: list[int] = []

    async def edit_message(self, entity, **kw):
        if entity == TARGET_A:
            raise errors.FloodWaitError(request=None)
        self.edited.append(entity)


class _FloodOnADeleteClient:
    def __init__(self):
        self.deleted: list[int] = []

    async def delete_messages(self, entity, message_ids):
        if entity == TARGET_A:
            raise errors.FloodWaitError(request=None)
        self.deleted.append(entity)


def _processor(db, client, targets):
    return EventProcessor(
        chat_mapping={SOURCE: {t: [_direction()] for t in targets}},
        database=db,
        client=client,
        logger=logging.getLogger("test.floodpropagate"),
    )


def test_edit_message_flood_on_one_target_does_not_abort_the_others():
    db = run(InMemoryDatabase())
    run(db.insert(MirrorMessage(100, SOURCE, 5000, TARGET_A)))
    run(db.insert(MirrorMessage(100, SOURCE, 6000, TARGET_B)))
    client = _FloodOnAEditClient()
    proc = _processor(db, client, [TARGET_A, TARGET_B])
    msg = make_message("hi", channel_id=1000)
    msg.id = 100

    run(proc.edit_message(SOURCE, msg, "link"))  # must not raise

    assert client.edited == [TARGET_B]


class _AlwaysFloodsFilter:
    """Stands in for a re-uploading filter (e.g. DocumentFilenameFilter/
    WatermarkRemovalFilter) whose FloodWaitError comes from filters.process
    itself, not from client.edit_message."""

    async def process(self, entity, event_type):
        raise errors.FloodWaitError(request=None)


def test_edit_message_flood_from_filters_process_does_not_abort_the_others():
    """A flood can also come from config.filters.process (e.g. a re-uploading
    filter), not just from client.edit_message itself — that path must be
    guarded the same way."""
    db = run(InMemoryDatabase())
    run(db.insert(MirrorMessage(100, SOURCE, 5000, TARGET_A)))
    run(db.insert(MirrorMessage(100, SOURCE, 6000, TARGET_B)))

    edited = []

    class _RecordingClient:
        async def edit_message(self, entity, **kw):
            edited.append(entity)

    proc = EventProcessor(
        chat_mapping={
            SOURCE: {
                TARGET_A: [DirectionConfig(
                    disable_delete=False, disable_edit=False,
                    filters=_AlwaysFloodsFilter(),
                )],
                TARGET_B: [_direction()],
            }
        },
        database=db,
        client=_RecordingClient(),
        logger=logging.getLogger("test.floodpropagate"),
    )
    msg = make_message("hi", channel_id=1000)
    msg.id = 100

    run(proc.edit_message(SOURCE, msg, "link"))  # must not raise

    assert edited == [TARGET_B]


def test_delete_message_flood_on_one_channel_does_not_abort_the_others():
    db = run(InMemoryDatabase())
    run(db.insert(MirrorMessage(100, SOURCE, 5000, TARGET_A)))
    run(db.insert(MirrorMessage(200, SOURCE, 6000, TARGET_B)))
    client = _FloodOnADeleteClient()
    proc = _processor(db, client, [TARGET_A, TARGET_B])

    run(proc.delete_message(SOURCE, [100, 200]))  # must not raise

    assert client.deleted == [TARGET_B]
    # TARGET_B's delete succeeded and needed no other channel -> purged.
    assert run(db.get_messages(200, SOURCE)) == []
    # TARGET_A flooded (never actually deleted on Telegram) -> kept for retry.
    assert len(run(db.get_messages(100, SOURCE))) == 1
