"""L5: a DM sender's display name is attacker-controlled and must be collapsed /
capped before it goes into the tech channel."""

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
