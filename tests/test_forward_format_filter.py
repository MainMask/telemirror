"""ForwardFormatFilter validates its format string at construction, so a broken
config fails fast instead of silently dropping every message at runtime."""

import pytest

from telemirror.messagefilters.messagefilters import (
    ForwardFormatFilter,
    MappedNameForwardFormat,
)


def test_valid_formats_accepted():
    ForwardFormatFilter()  # default
    ForwardFormatFilter("{message_text}\n\nfrom [{channel_name}]({message_link})")
    ForwardFormatFilter("{message_text} — {sender_title} {sender_username}")


@pytest.mark.parametrize("bad", ["{oops}", "{", "}", "{message_text} {0}"])
def test_invalid_format_rejected(bad):
    with pytest.raises(ValueError):
        ForwardFormatFilter(bad)


def test_mapped_name_variant_also_validates():
    with pytest.raises(ValueError):
        MappedNameForwardFormat(mapped={}, format="{oops}")
