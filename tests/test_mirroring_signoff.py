"""Sign-off regression tests for telemirror/mirroring.py covering fixes from
earlier review passes that lacked a dedicated test (see REVIEW.md)."""

import logging
from types import SimpleNamespace

from telethon.tl import types

import telemirror.mirroring as mirroring
from config import DirectionConfig
from telemirror.messagefilters import EmptyMessageFilter
from telemirror.mirroring import EventHandlers, EventProcessor
from telemirror.storage import InMemoryDatabase
from tests.conftest import make_message, run

SOURCE = -1001000000000
TARGET = -1002000000001


def _cfg(**kw):
    return DirectionConfig(
        disable_delete=False,
        disable_edit=False,
        filters=EmptyMessageFilter(),
        **kw,
    )


def test_restricted_saving_source_is_skipped(monkeypatch, caplog):
    """A noforwards source with copy-mode filters that don't allow restricted
    content: nothing is sent or tracked (pass 1: bool() wrap on the guard)."""
    db = run(InMemoryDatabase())

    sent = []

    async def fake_send_message(client, entity, message, **kw):
        sent.append(entity)
        return types.Message(id=1, peer_id=types.PeerChannel(1), message="x")

    monkeypatch.setattr(mirroring, "send_message", fake_send_message)

    proc = EventProcessor(
        chat_mapping={SOURCE: {TARGET: [_cfg()]}},
        database=db,
        client=object(),
        logger=logging.getLogger("test.restricted"),
    )
    msg = make_message("hi", channel_id=1000)
    msg._chat = SimpleNamespace(noforwards=True)

    with caplog.at_level(logging.WARNING, logger="test.restricted"):
        run(proc.new_message(SOURCE, msg, "link"))

    assert sent == []
    assert run(db.get_messages(msg.id, SOURCE)) == []
    assert any("restricted saving content" in r.message for r in caplog.records)


def test_event_message_link_handles_deleted_event():
    """MessageDeleted events fall to the else branch (pass 4: elif -> else,
    removed the unbound-variable path)."""

    class FakeClient:
        def add_event_handler(self, *a, **kw):
            pass

    handlers = EventHandlers(
        client=FakeClient(), chats=[SOURCE], processor=object()
    )
    fake_event = SimpleNamespace(chat_id=-1001234567890, deleted_id=42)

    link = handlers.event_message_link(fake_event)

    assert link == mirroring.private_message_link(-1001234567890, 42)
