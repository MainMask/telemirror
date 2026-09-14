"""L5: a DM sender's display name is attacker-controlled and must be collapsed /
capped before it goes into the tech channel."""

import logging

from telethon.tl import types

from telemirror.mirroring import EventHandlers
from tests.conftest import run


class FakeClient:
    def add_event_handler(self, *a, **kw):
        pass


class FakeSender:
    def __init__(self):
        self.sent = []

    async def send_message(self, channel, text):
        self.sent.append((channel, text))


def _handlers(sender):
    return EventHandlers(
        client=FakeClient(),
        chats=[],
        processor=object(),
        sender=sender,
        tech_channel=-100999,
    )


def test_sender_name_is_sanitized():
    sender = FakeSender()
    h = _handlers(sender)

    user = types.User(
        id=1, first_name="evil\n\n\n💥 FAKE ALERT " + "x" * 500, last_name=None,
        username="mallory",
    )

    class Event:
        async def get_sender(self):
            return user

    run(h.on_private_message(Event()))

    (_, text) = sender.sent[0]
    assert "\n" not in text
    assert "@mallory" in text
    assert len(text) < 200  # capped, not a 500-char blob


def test_notification_failure_is_logged_not_left_unhandled(caplog):
    """Unlike every other event handler in this module (all routed through
    EventProcessor.__handle_exceptions or an explicit try/except),
    on_private_message had no error handling at all — a failure notifying
    TECH_CHANNEL (e.g. FloodWait, bot removed from the channel) must be
    logged through the same logger the rest of the module uses, not left to
    propagate into Telethon's own default per-handler logging (a different
    logger, never reaching TECH_CHANNEL via TelegramLogHandler)."""

    class FailingSender:
        async def send_message(self, channel, text):
            raise RuntimeError("boom")

    class ProcessorStub:
        logger = logging.getLogger("test.on_private_message")

    h = EventHandlers(
        client=FakeClient(),
        chats=[],
        processor=ProcessorStub(),
        sender=FailingSender(),
        tech_channel=-100999,
    )

    user = types.User(id=1, first_name="X", last_name=None, username=None)

    class Event:
        async def get_sender(self):
            return user

    with caplog.at_level(logging.ERROR, logger="test.on_private_message"):
        run(h.on_private_message(Event()))  # must not raise

    assert any(
        "private message" in r.message.lower() and "boom" in r.message
        for r in caplog.records
    )
