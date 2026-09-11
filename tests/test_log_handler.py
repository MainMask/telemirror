"""A6: TelegramLogHandler must not leak cooldown entries for one-off messages."""

import asyncio

from telemirror.mirroring import TelegramLogHandler


class FakeClient:
    def __init__(self, loop):
        self.loop = loop


def test_prune_cooldowns_drops_expired():
    loop = asyncio.new_event_loop()
    try:
        h = TelegramLogHandler(FakeClient(loop), channel=-100)
        now = loop.time()
        h._cooldown_until = {
            "old-1": now - 10,
            "old-2": now - 1,
            "fresh": now + 30,
        }
        h._enqueue("brand new message")

        assert "old-1" not in h._cooldown_until
        assert "old-2" not in h._cooldown_until
        assert "fresh" in h._cooldown_until
    finally:
        loop.close()


def test_send_task_is_referenced():
    loop = asyncio.new_event_loop()
    try:
        h = TelegramLogHandler(FakeClient(loop), channel=-100)
        h._counts["msg"] = 1

        async def drive():
            h._send("msg")
            assert h._tasks, "send task must be strongly referenced"
            await asyncio.sleep(0)

        loop.run_until_complete(drive())
        assert h._tasks == set()  # done-callback cleaned it up
    finally:
        loop.close()
