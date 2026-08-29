"""A4: filters must not crash on media messages with no caption (``message.message``
is ``None``)."""

from telethon import events
from telethon.tl import types

from telemirror.messagefilters.messagefilters import ForwardFormatFilter, UrlMessageFilter
from tests.conftest import make_message, run


def test_url_filter_handles_none_text():
    msg = make_message(text=None)
    action, res = run(
        UrlMessageFilter(blacklist={"t.me"})._process_message(
            msg, events.NewMessage.Event
        )
    )
    assert res.message == ""


def test_forward_format_filter_handles_none_text():
    msg = make_message(text=None)
    fmt = ForwardFormatFilter(format="{message_text}\n\n**fwd**")
    action, res = run(fmt._process_message(msg, events.NewMessage.Event))
    assert res.message.endswith("fwd")
    assert "None" not in res.message
    assert res.entities and any(
        isinstance(e, types.MessageEntityBold) for e in res.entities
    )
