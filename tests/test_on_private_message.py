"""A private message to the account is reported to the panel's admins; the
sender's display name is attacker-controlled and must be collapsed / capped
(the notice is plain text — see test_notify for no markup)."""

import logging

from telethon.tl import types

from telemirror.mirroring import EventHandlers
from tests.conftest import run


class FakeClient:
    def add_event_handler(self, *a, **kw):
        pass


class FakeNotifier:
    def __init__(self):
        self.sent = []

    async def send(self, body):
        self.sent.append(body)
        return True


def _event(user):
    class Event:
        async def get_sender(self):
            return user
    return Event()


def test_sender_name_is_sanitized():
    notifier = FakeNotifier()
    h = EventHandlers(client=FakeClient(), chats=[], processor=object(), notifier=notifier)
    user = types.User(
        id=1, first_name="evil\n\n\n💥 FAKE ALERT " + "x" * 500, last_name=None,
        username="mallory",
    )
    run(h.on_private_message(_event(user)))
    (text,) = notifier.sent
    assert text.startswith("📩 Аккаунту написали в личку:")
    assert "\n" not in text
    assert "@mallory" in text
    assert len(text) < 200  # capped, not a 500-char blob


def test_no_notifier_no_private_message_handler():
    added = []

    class Recording(FakeClient):
        def add_event_handler(self, callback, *a, **kw):
            added.append(callback.__name__)

    EventHandlers(client=Recording(), chats=[], processor=object())
    assert "on_private_message" not in added


def test_notification_failure_is_logged_not_left_unhandled(caplog):
    """Unlike every other event handler in this module (all routed through
    EventProcessor.__handle_exceptions or an explicit try/except), a failure
    here must be logged through the same logger the rest of the module uses,
    not left to propagate into Telethon's own default per-handler logging."""

    class FailingNotifier:
        async def send(self, body):
            raise RuntimeError("boom")

    class ProcessorStub:
        logger = logging.getLogger("test.on_private_message")

    h = EventHandlers(client=FakeClient(), chats=[], processor=ProcessorStub(), notifier=FailingNotifier())
    user = types.User(id=1, first_name="X", last_name=None, username=None)
    with caplog.at_level(logging.ERROR, logger="test.on_private_message"):
        run(h.on_private_message(_event(user)))  # must not raise
    assert any("private message" in r.message.lower() and "boom" in r.message for r in caplog.records)
