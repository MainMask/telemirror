import pytest
from telethon import events
from telethon.tl import types

from telemirror.messagefilters.messagefilters import (
    AllowWithKeywordsFilter,
    KeywordReplaceFilter,
    SkipWithKeywordsFilter,
)
from tests.conftest import entity_text, make_message, run


def _process(f, message):
    return run(f._process_message(message, events.NewMessage.Event))


def test_plain_keyword_replaced():
    f = KeywordReplaceFilter({"google.com": "bing.com"})
    _, res = _process(f, make_message("visit google.com today"))
    assert res.message == "visit bing.com today"


def test_regex_keyword_keeps_configured_casing():
    """A1: an ``r'...'`` handle replacement must not be down-cased to match the
    lowercase source token."""
    f = KeywordReplaceFilter({"r'@alliance1000'": "@Archonor"})
    _, res = _process(f, make_message("Contact @alliance1000 now"))
    assert res.message == "Contact @Archonor now"


def test_multiple_length_changing_keywords_keep_entity_alignment():
    """A2: two length-changing replacements must not corrupt a trailing entity's
    offset."""
    msg = make_message(
        "aaa BBB ccc",
        entities=[types.MessageEntityBold(offset=8, length=3)],  # "ccc"
    )
    f = KeywordReplaceFilter({"r'aaa'": "XXXXXXXX", "r'BBB'": "Y"})
    _, res = _process(f, msg)

    assert res.message == "XXXXXXXX Y ccc"
    (bold,) = res.entities
    assert entity_text(res, bold) == "ccc"


def test_regex_replacement_with_backref():
    f = KeywordReplaceFilter({r"r'(\d+)px'": r"\1 pixels"})
    _, res = _process(f, make_message("width 12px"))
    assert res.message == "width 12 pixels"


def test_no_text_passes_through():
    f = KeywordReplaceFilter({"a": "b"})
    action, res = _process(f, make_message(""))
    assert res.message == ""


@pytest.mark.parametrize("cls", [SkipWithKeywordsFilter, AllowWithKeywordsFilter])
def test_empty_keywords_rejected(cls):
    """An empty set would compile to a match-everything regex — fail fast instead."""
    with pytest.raises(ValueError):
        cls(set())


def test_skip_with_keywords_still_works():
    from telemirror.messagefilters.base import FilterAction

    f = SkipWithKeywordsFilter({"spam"})
    action, _ = _process(f, make_message("this is spam"))
    assert action is FilterAction.DISCARD
    action, _ = _process(f, make_message("this is fine"))
    assert action is FilterAction.CONTINUE
