"""edit_message shares two fixes originally built for delete_message/the
new_message fan-out loop:

1. It must wait for a still in-progress new_message/new_album fan-out of the
   same source message before reading the DB (same race as delete_message:
   an edit arriving right after the post could otherwise only see whichever
   targets were already tracked).
2. A bug in one target's filter chain must not abort delivering the edit to
   the remaining targets (same fix as new_message/new_album's fan-out loop)."""

import asyncio
import logging

from config import DirectionConfig
from telemirror.messagefilters import EmptyMessageFilter
from telemirror.mirroring import EventProcessor
from telemirror.storage import InMemoryDatabase, MirrorMessage
from tests.conftest import make_message, run

SOURCE = -1001000000000
TARGET = -1002000000001
TARGET_A = -1002000000001
TARGET_B = -1002000000002


def _cfg(filters=None):
    return DirectionConfig(
        disable_delete=False, disable_edit=False, filters=filters or EmptyMessageFilter()
    )


class _RecordingClient:
    def __init__(self):
        self.edited: list[int] = []

    async def edit_message(self, entity, message, **kw):
        self.edited.append(message)


def test_edit_message_waits_for_in_progress_new_message_fanout():
    db = run(InMemoryDatabase())
    proc = EventProcessor(
        chat_mapping={SOURCE: {TARGET_A: [_cfg()]}},
        database=db,
        client=_RecordingClient(),
        logger=logging.getLogger("test.editrace"),
    )
    key = (SOURCE, 1)

    async def scenario():
        events = []

        async def slow_fanout():
            async with proc._track_fanout([key]):
                events.append("fanout_start")
                await asyncio.sleep(0.02)
                # Only after the fan-out is fully done is TARGET_A's row
                # actually persisted — simulate that here.
                run_insert = db.insert_batch(
                    [MirrorMessage(1, SOURCE, 900, TARGET_A)]
                )
                await run_insert
                events.append("fanout_end")

        fanout_task = asyncio.ensure_future(slow_fanout())
        await asyncio.sleep(0)  # let the fan-out register and start sleeping

        msg = make_message("hello", channel_id=1000)
        msg.id = 1
        edit_task = asyncio.ensure_future(
            proc.edit_message(SOURCE, msg, "https://t.me/c/1000/1")
        )
        await asyncio.sleep(0)
        # edit_message must be blocked on the pending fan-out, not already
        # done — the DB has no row yet at this point.
        assert not edit_task.done()

        await asyncio.gather(fanout_task, edit_task)
        events.append("edit_done")
        assert events == ["fanout_start", "fanout_end", "edit_done"]

    run(scenario())

    client = proc._client
    assert client.edited == [900]


class _BoomFilter:
    restricted_content_allowed = False

    async def process(self, entity, event_type):
        raise RuntimeError("boom")


def test_edit_message_continues_past_one_targets_filter_bug(caplog):
    db = run(InMemoryDatabase())
    run(db.insert_batch([
        MirrorMessage(1, SOURCE, 900, TARGET_A),
        MirrorMessage(1, SOURCE, 901, TARGET_B),
    ]))

    client = _RecordingClient()
    configs = {
        TARGET_A: [_cfg()],
        TARGET_B: [_cfg(filters=_BoomFilter())],
    }
    proc = EventProcessor(
        chat_mapping={SOURCE: configs},
        database=db,
        client=client,
        logger=logging.getLogger("test.editbug"),
    )

    msg = make_message("hello", channel_id=1000)
    msg.id = 1

    with caplog.at_level(logging.ERROR, logger="test.editbug"):
        run(proc.edit_message(SOURCE, msg, "https://t.me/c/1000/1"))

    assert client.edited == [900]
    assert any("Error while filtering edited message" in r.message for r in caplog.records)
