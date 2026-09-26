"""A6: TelegramLogHandler must not leak cooldown entries for one-off messages."""

import asyncio

from telemirror.mirroring import TelegramLogHandler


class FakeClient:
    def __init__(self, loop):
        self.loop = loop
        self.sent = []

    async def send_message(self, channel, msg, **kw):
        self.sent.append((channel, msg, kw))


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


def test_do_send_disables_markdown_parsing():
    """Log text is never authored as markdown: `__`/`**`/`[..](..)` inside an
    exception message or a path must reach TECH_CHANNEL verbatim."""
    loop = asyncio.new_event_loop()
    try:
        client = FakeClient(loop)
        h = TelegramLogHandler(client, channel=-100)
        loop.run_until_complete(h._do_send("__init__ failed: **x** [a](b)"))
        assert client.sent == [(-100, "__init__ failed: **x** [a](b)", {"parse_mode": None})]
    finally:
        loop.close()
