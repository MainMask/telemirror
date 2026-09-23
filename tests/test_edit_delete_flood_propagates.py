"""edit_message/delete_message are only reachable from live event handlers
(on_edit_message/on_deleted_message) and from _sync_broadcast_channel's
catch-up loop — neither has a retry wrapper for a FloodWaitError, unlike
new_message/new_album which past_mode.py replays and retries. So a flood on
one target must be logged and NOT propagate: propagating would only abort
processing of every other, un-flooded target for the same edit/delete, with
no compensating benefit (nothing upstream would ever retry it anyway)."""

import logging

import pytest
from telethon import errors
from telethon.tl import types

from config import DirectionConfig
from telemirror.messagefilters import EmptyMessageFilter
from telemirror.messagefilters.base import FilterAction, FilterResult
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


class _FloodOnceEditClient:
    """Floods on the first edit_message call, succeeds on every call after —
    stands in for a send-time FloodWaitError (as opposed to one raised from
    filters.process, covered above)."""

    def __init__(self):
        self.edited: list[int] = []
        self._calls = 0

    async def edit_message(self, entity, **kw):
        self._calls += 1
        if self._calls == 1:
            raise errors.FloodWaitError(request=None)
        self.edited.append(entity)


def test_edit_message_gives_up_on_remaining_siblings_when_send_floods():
    """Same legacy/orphaned-row setup as the discard case above, but the
    first candidate's actual client.edit_message() call floods instead of
    its filter discarding. Unlike a discard, a flood must NOT try the next
    sibling config: flood_sleep_threshold=300 means only a long wait reaches
    this handler, and Telegram's edit flood limit isn't scoped per sibling
    target, so an immediate retry on the same client would almost certainly
    burn another request into the same active flood window."""
    db = run(InMemoryDatabase())
    run(db.insert(MirrorMessage(100, SOURCE, 5000, TARGET_A)))  # no topic recorded -> no exact match
    client = _FloodOnceEditClient()

    proc = EventProcessor(
        chat_mapping={
            SOURCE: {
                TARGET_A: [
                    DirectionConfig(
                        disable_delete=False, disable_edit=False,
                        filters=EmptyMessageFilter(), from_topic_id=5,
                    ),
                    DirectionConfig(
                        disable_delete=False, disable_edit=False,
                        filters=EmptyMessageFilter(), from_topic_id=6,
                    ),
                ]
            }
        },
        database=db,
        client=client,
        logger=logging.getLogger("test.floodpropagate"),
    )
    msg = make_message("hi", channel_id=1000)
    msg.id = 100

    run(proc.edit_message(SOURCE, msg, "link"))  # must not raise

    assert client.edited == []  # gave up after the flood, second config never tried
    assert client._calls == 1


def _doc_media(file_reference: bytes) -> types.MessageMediaDocument:
    return types.MessageMediaDocument(
        document=types.Document(
            id=42, access_hash=0, file_reference=file_reference, date=None,
            mime_type="application/pdf", size=1024, dc_id=1, attributes=[],
        )
    )


class _StaleThenFloodEditClient:
    """First edit_message call goes stale (FileReferenceExpiredError); the
    refreshed retry then floods. Stands in for a flood raised from the
    file-reference-refresh retry path, not the primary attempt."""

    def __init__(self, fresh_message):
        self._fresh_message = fresh_message
        self.edit_attempts: list[int] = []
        self.get_messages_calls = []

    async def edit_message(self, entity, message, file=None, **kw):
        self.edit_attempts.append(entity)
        if len(self.edit_attempts) == 1:
            raise errors.FileReferenceExpiredError(request=None)
        if len(self.edit_attempts) == 2:
            raise errors.FloodWaitError(request=None)
        # third attempt: the second sibling config's edit succeeds outright.

    async def get_messages(self, entity, ids):
        self.get_messages_calls.append((entity, ids))
        return self._fresh_message


def test_edit_message_gives_up_on_remaining_siblings_when_the_refresh_retry_floods():
    """Same legacy/orphaned-row, two-sibling-config setup as the send-time
    flood case above, but the flood happens on the RETRY after a
    FileReferenceExpiredError refresh, not the primary attempt. Same
    give-up-immediately reasoning applies: the nested retry must not fall
    back to the next sibling config either."""
    db = run(InMemoryDatabase())
    run(db.insert(MirrorMessage(100, SOURCE, 5000, TARGET_A)))  # no topic recorded -> no exact match

    fresh_message = make_message(media=_doc_media(b"fresh-reference"), channel_id=1000)
    client = _StaleThenFloodEditClient(fresh_message)

    proc = EventProcessor(
        chat_mapping={
            SOURCE: {
                TARGET_A: [
                    DirectionConfig(
                        disable_delete=False, disable_edit=False,
                        filters=EmptyMessageFilter(), from_topic_id=5,
                    ),
                    DirectionConfig(
                        disable_delete=False, disable_edit=False,
                        filters=EmptyMessageFilter(), from_topic_id=6,
                    ),
                ]
            }
        },
        database=db,
        client=client,
        logger=logging.getLogger("test.floodpropagate"),
    )
    msg = make_message(media=_doc_media(b"stale-reference"), channel_id=1000)
    msg.id = 100
    msg._client = client

    run(proc.edit_message(SOURCE, msg, "link"))  # must not raise

    # 1st config only: stale reference, then refreshed retry floods and gives
    # up — the 2nd config's edit_message is never called.
    assert len(client.edit_attempts) == 2
    assert client.edit_attempts == [TARGET_A, TARGET_A]


class _AlwaysDiscardsFilter:
    async def process(self, entity, event_type):
        return FilterResult(FilterAction.DISCARD, entity)


@pytest.mark.parametrize(
    "rows, configs, expected_edited",
    [
        pytest.param(
            [
                MirrorMessage(100, SOURCE, 5000, TARGET_A, mirror_topic_id=1),
                MirrorMessage(100, SOURCE, 5001, TARGET_A, mirror_topic_id=2),
            ],
            [
                DirectionConfig(
                    disable_delete=False, disable_edit=True,
                    filters=EmptyMessageFilter(), to_topic_id=1,
                ),
                DirectionConfig(
                    disable_delete=False, disable_edit=False,
                    filters=EmptyMessageFilter(), to_topic_id=2,
                ),
            ],
            [5001],
            id="respects_the_specific_topics_disable_edit",
            # TARGET_A is reached by two topic-scoped directions: topic 1 is
            # disable_edit=True (protected), topic 2 is not. A row belonging
            # to topic 1 must never be edited just because topic 2's config
            # for the same channel happens to be unprotected — picking "any
            # non-disabled config for the channel" (the pre-mirror_topic_id
            # behavior) would wrongly edit it.
        ),
        pytest.param(
            [MirrorMessage(100, SOURCE, 5000, TARGET_A)],  # no topic recorded -> no exact match
            [
                DirectionConfig(
                    disable_delete=False, disable_edit=False,
                    filters=_AlwaysDiscardsFilter(),  # type: ignore[arg-type]  # only .process() is called; doesn't need the rest of the Protocol
                    from_topic_id=5,
                ),
                DirectionConfig(
                    disable_delete=False, disable_edit=False,
                    filters=EmptyMessageFilter(), from_topic_id=6,
                ),
            ],
            [5000],
            id="retries_a_sibling_config_when_the_first_discards",
            # A legacy/orphaned row (no exact from/to topic match for either
            # config) must retry every non-disabled config in list order,
            # same as before the topic migration: _config_for_topic itself
            # only returns a single config, but edit_message uses
            # _configs_to_try_for_topic and keeps trying siblings when one's
            # filter discards the edit instead of giving up on the whole row.
        ),
        pytest.param(
            [
                MirrorMessage(100, SOURCE, 5000, TARGET_A, source_topic_id=None),
                MirrorMessage(100, SOURCE, 5001, TARGET_A, source_topic_id=20),
            ],
            [
                DirectionConfig(
                    disable_delete=False, disable_edit=True,
                    filters=EmptyMessageFilter(), from_topic_id=None,
                ),
                DirectionConfig(
                    disable_delete=False, disable_edit=False,
                    filters=EmptyMessageFilter(), from_topic_id=20,
                ),
            ],
            [5001],
            id="disambiguates_via_source_topic_when_destination_collides",
            # TARGET_A is reached by two directions that BOTH have
            # to_topic_id=None (a non-forum target) — mirror_topic_id alone
            # can't tell their rows apart. They differ only in from_topic_id:
            # general (disable_edit=True, protects everything) and scoped
            # (disable_edit=False, only topic 20). A row produced by `scoped`
            # must be edited using `scoped`'s own settings, not silently
            # inherit `general`'s just because it's first in the list.
        ),
    ],
)
def test_edit_message_topic_scoped_disambiguation(rows, configs, expected_edited):
    db = run(InMemoryDatabase())
    run(db.insert_batch(rows))

    edited = []

    class _RecordingClient:
        async def edit_message(self, entity, message, **kw):
            edited.append(message)

    proc = EventProcessor(
        chat_mapping={SOURCE: {TARGET_A: configs}},
        database=db,
        client=_RecordingClient(),
        logger=logging.getLogger("test.topicdisambiguate"),
    )
    msg = make_message("hi", channel_id=1000)
    msg.id = 100

    run(proc.edit_message(SOURCE, msg, "link"))

    assert edited == expected_edited


def test_delete_message_disambiguates_via_source_topic_when_destination_collides():
    """Same colliding-destination setup as the edit_message test above, for
    delete_message: only the row produced by the unprotected `scoped`
    direction is deleted."""
    db = run(InMemoryDatabase())
    run(db.insert_batch([
        MirrorMessage(100, SOURCE, 5000, TARGET_A, source_topic_id=None),
        MirrorMessage(100, SOURCE, 5001, TARGET_A, source_topic_id=20),
    ]))

    deleted = []

    class _RecordingClient:
        async def delete_messages(self, entity, message_ids):
            deleted.extend(message_ids)

    proc = EventProcessor(
        chat_mapping={
            SOURCE: {
                TARGET_A: [
                    DirectionConfig(
                        disable_delete=True, disable_edit=False,
                        filters=EmptyMessageFilter(), from_topic_id=None,
                    ),
                    DirectionConfig(
                        disable_delete=False, disable_edit=False,
                        filters=EmptyMessageFilter(), from_topic_id=20,
                    ),
                ]
            }
        },
        database=db,
        client=_RecordingClient(),
        logger=logging.getLogger("test.sourcetopicdisambiguate"),
    )

    run(proc.delete_message(SOURCE, [100]))

    assert deleted == [5001]  # only the `scoped` (unprotected) mirror was deleted
    remaining = run(db.get_messages(100, SOURCE))
    assert [m.mirror_id for m in remaining] == [5000]  # protected row survives


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
