"""A3: EventProcessor.delete_message must remove the DB mappings for the deleted
source messages (not the last target's mirror ids)."""

import logging

from config import DirectionConfig
from telemirror.messagefilters import EmptyMessageFilter
from telemirror.mirroring import EventProcessor
from telemirror.storage import InMemoryDatabase, MirrorMessage
from tests.conftest import run

SOURCE = -1001111111111
TARGET_A = -1002222222222
TARGET_B = -1003333333333


class FakeClient:
    def __init__(self):
        self.deleted: list[tuple[int, list[int]]] = []

    async def delete_messages(self, entity, message_ids):
        self.deleted.append((entity, list(message_ids)))


def _direction(disable_delete=False):
    return DirectionConfig(
        disable_delete=disable_delete,
        disable_edit=False,
        filters=EmptyMessageFilter(),
    )


def _processor(db, mapping):
    return EventProcessor(
        chat_mapping=mapping,
        database=db,
        client=FakeClient(),
        logger=logging.getLogger("test"),
    )


def test_delete_removes_db_mapping_for_all_targets():
    db = run(InMemoryDatabase())
    # source msg 100 mirrored to two targets with different mirror ids
    run(db.insert(MirrorMessage(100, SOURCE, 5000, TARGET_A)))
    run(db.insert(MirrorMessage(100, SOURCE, 9000, TARGET_B)))

    mapping = {SOURCE: {TARGET_A: [_direction()], TARGET_B: [_direction()]}}
    proc = _processor(db, mapping)

    run(proc.delete_message(SOURCE, [100]))

    # both target deletions issued
    assert {c for c, _ in proc._client.deleted} == {TARGET_A, TARGET_B}
    # and the mapping row is gone
    assert run(db.get_messages(100, SOURCE)) == []


def test_delete_skips_db_purge_when_all_disabled():
    db = run(InMemoryDatabase())
    run(db.insert(MirrorMessage(100, SOURCE, 5000, TARGET_A)))
    mapping = {SOURCE: {TARGET_A: [_direction(disable_delete=True)]}}
    proc = _processor(db, mapping)

    run(proc.delete_message(SOURCE, [100]))

    assert proc._client.deleted == []
    assert run(db.get_messages(100, SOURCE)) != []
