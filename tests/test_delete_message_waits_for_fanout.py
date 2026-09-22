"""delete_message must wait for a still in-progress new_message fan-out of the
same source message before reading the DB — otherwise a source message
deleted moments after posting can race the fan-out: delete_message only sees
whichever targets were already tracked, and any target reached after its DB
read is sent to but never deleted (an orphaned copy left forever)."""

import asyncio
import logging

from telethon.tl import types

import telemirror.mirroring as mirroring
from config import DirectionConfig
from telemirror.messagefilters import EmptyMessageFilter
from telemirror.mirroring import EventProcessor
from telemirror.storage import InMemoryDatabase
from tests.conftest import make_message, run

SOURCE = -1001000000000
TARGET_A = -1002000000001
TARGET_B = -1002000000002


class _RecordingClient:
    def __init__(self):
        self.deleted: list[tuple[int, list[int]]] = []

    async def delete_messages(self, entity, message_ids):
        self.deleted.append((entity, list(message_ids)))


def _cfg():
    return DirectionConfig(
        disable_delete=False, disable_edit=False, filters=EmptyMessageFilter()
    )


def test_delete_message_waits_for_in_progress_new_message(monkeypatch):
    db = run(InMemoryDatabase())
    client = _RecordingClient()

    started_target_b = asyncio.Event()
    release_target_b = asyncio.Event()
    db_read_order: list[str] = []

    async def fake_send_message(send_client, entity, message, **kw):
        if entity == TARGET_B:
            started_target_b.set()
            await release_target_b.wait()
        return types.Message(id=999, peer_id=types.PeerChannel(1), message="x")

    monkeypatch.setattr(mirroring, "send_message", fake_send_message)

    real_get_messages_batch = db.get_messages_batch

    async def spy_get_messages_batch(*a, **kw):
        db_read_order.append("delete_read_db")
        return await real_get_messages_batch(*a, **kw)

    monkeypatch.setattr(db, "get_messages_batch", spy_get_messages_batch)

    proc = EventProcessor(
        chat_mapping={SOURCE: {TARGET_A: [_cfg()], TARGET_B: [_cfg()]}},
        database=db,
        client=client,
        logger=logging.getLogger("test.deleterace"),
    )

    msg = make_message("hello", channel_id=1000)

    async def scenario():
        new_message_task = asyncio.ensure_future(
            proc.new_message(SOURCE, msg, "https://t.me/c/1000/1")
        )
        # Wait until the fan-out has reached (and is blocked mid-send on)
        # TARGET_B — TARGET_A is already sent and tracked at this point.
        await started_target_b.wait()

        delete_task = asyncio.ensure_future(proc.delete_message(SOURCE, [msg.id]))
        await asyncio.sleep(0)  # let delete_message run up to the pending-future await
        # delete_message must not have read the DB yet — the fan-out isn't done.
        assert db_read_order == []

        release_target_b.set()
        await asyncio.gather(new_message_task, delete_task)

    run(scenario())

    # Both targets were reached by the fan-out AND both got deleted — the
    # race window (delete reading the DB before TARGET_B was tracked) never
    # got a chance to bite.
    assert {c for c, _ in client.deleted} == {TARGET_A, TARGET_B}
    assert db_read_order == ["delete_read_db"]
