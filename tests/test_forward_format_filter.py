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
