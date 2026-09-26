"""ForwardFormatFilter validates its format string at construction, so a broken
config fails fast instead of silently dropping every message at runtime."""

import pytest
from telethon import events

from telemirror.messagefilters.messagefilters import (
    ForwardFormatFilter,
    MappedNameForwardFormat,
)
from tests.conftest import make_message, run


def test_valid_formats_accepted():
    ForwardFormatFilter()  # default
    ForwardFormatFilter("{message_text}\n\nfrom [{channel_name}]({message_link})")
    ForwardFormatFilter("{message_text} — {sender_title} {sender_username}")


@pytest.mark.parametrize(
    "bad", ["{oops}", "{", "}", "{message_text} {0}", "from [{channel_name}]({message_link})"]
)
def test_invalid_format_rejected(bad):
    with pytest.raises(ValueError):
        ForwardFormatFilter(bad)


def test_mapped_name_variant_also_validates():
    with pytest.raises(ValueError):
        MappedNameForwardFormat(mapped={}, format="{oops}")


def test_braces_in_channel_name_do_not_break_formatting():
    """A channel titled with literal ``{...}`` must not make the second
    substitution raise KeyError and silently drop the message."""
    msg = make_message("hi")
    f = MappedNameForwardFormat(
        mapped={msg.chat_id: "Deals {hot}"},
        format="{message_text}\n\nfrom {channel_name}",
    )
    _, res = run(f._process_message(msg, events.NewMessage.Event))
    assert res.message == "hi\n\nfrom Deals {hot}"


def test_astral_emoji_in_header_keeps_body_entities_aligned():
    """Telegram entity offsets are UTF-16 units: an astral emoji (🚀) in the
    header before {message_text} is 2 units, not 1 — the body's own entities
    must still cover their text after the header is prepended."""
    from telethon.tl import types

    from tests.conftest import entity_text

    msg = make_message("hi there", entities=[types.MessageEntityBold(offset=0, length=2)])
    f = MappedNameForwardFormat(
        {msg.chat_id: "🚀 Crypto"}, "{channel_name}\n{message_text}"
    )
    _, out = run(f.process(msg, events.NewMessage.Event))
    assert out.message == "🚀 Crypto\nhi there"
    assert entity_text(out, out.entities[0]) == "hi"


@pytest.mark.parametrize(
    "fmt, body, expected",
    [
        # header entity exactly wrapping the placeholder
        ("**{message_text}**\n\nfrom x", "hello world", "hello world"),
        # header entity starting before the placeholder and containing it
        ("__Note: {message_text}__", "a body longer than the placeholder", "Note: a body longer than the placeholder"),
        # and a body shorter than the placeholder
        ("__Note: {message_text}__", "hi", "Note: hi"),
    ],
)
def test_header_entity_wrapping_the_body_is_resized(fmt, body, expected):
    """A format entity that contains ``{message_text}`` must stretch/shrink
    with the substituted body, not keep the placeholder's 14-unit length
    (Pass 21: ``**{message_text}**`` bolded ``'hello world\\n\\nf'``)."""
    from tests.conftest import entity_text

    msg = make_message(body)
    _, out = run(ForwardFormatFilter(fmt).process(msg, events.NewMessage.Event))
    assert [entity_text(out, e) for e in out.entities] == [expected]


def test_header_entity_after_the_body_still_shifts():
    from tests.conftest import entity_text

    msg = make_message("🚀 hello")
    _, out = run(
        ForwardFormatFilter("{message_text}\n\n**Forwarded** from x").process(
            msg, events.NewMessage.Event
        )
    )
    assert [entity_text(out, e) for e in out.entities] == ["Forwarded"]
