"""_fanout_inflight must track every in-flight fan-out for a given
(chat_id, message_id), not just the most recent one. A redelivered/duplicate
update for the same message id registers a second entry under the same key
while an earlier one is still running; a single-future-per-key design would
have the second registration silently overwrite the first, so a waiter
(delete_message/edit_message) checking that key would miss the still-running
earlier fan-out entirely."""

import asyncio
import logging

from telemirror.mirroring import EventProcessor
from telemirror.storage import InMemoryDatabase
from tests.conftest import run

SOURCE = -1001111111111


def test_delete_waits_for_every_overlapping_fanout_of_the_same_message():
    db = run(InMemoryDatabase())
    proc = EventProcessor(
        chat_mapping={}, database=db, client=object(), logger=logging.getLogger("test.inflight")
    )
    key = (SOURCE, 1)

    async def scenario():
        order = []

        async def slow_fanout_a():
            async with proc._track_fanout([key]):
                order.append("a_start")
                await asyncio.sleep(0.05)
                order.append("a_end")

        async def fast_fanout_b():
            async with proc._track_fanout([key]):
                order.append("b_start")
                order.append("b_end")

        task_a = asyncio.ensure_future(slow_fanout_a())
        await asyncio.sleep(0)  # let A register and start its sleep
        task_b = asyncio.ensure_future(fast_fanout_b())
        await task_b  # B (the "duplicate delivery") finishes while A is still running

        # With the fix: A's registration must still be visible after B's own
        # registration+cleanup for the same key has come and gone.
        assert key in proc._fanout_inflight
        pending = list(proc._fanout_inflight.get(key, []))
        assert len(pending) == 1  # only A remains; B's own entry was removed on its own cleanup

        await asyncio.gather(task_a, *pending)
        assert order == ["a_start", "b_start", "b_end", "a_end"]
        assert key not in proc._fanout_inflight

    run(scenario())
