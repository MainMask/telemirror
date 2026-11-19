import pytest
from telethon import events
from telethon.tl import types

from telemirror.messagefilters.base import FilterAction
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


def test_broken_regex_keyword_raises_value_error():
    with pytest.raises(ValueError):
        KeywordReplaceFilter({"r'(unclosed'": "x"})
    with pytest.raises(ValueError):
        SkipWithKeywordsFilter({"r'[z-a]'"})


def test_replacement_referencing_nonexistent_group_raises_value_error_at_construction():
    """A raw-regex rule whose replacement references a capture group the
    pattern doesn't have (e.g. `\\2` against a one-group pattern) must fail
    fast at construction — like a broken pattern already does — instead of
    raising a bare `re.error` out of `_apply_rule` the first time a real
    message happens to match."""
    with pytest.raises(ValueError):
        KeywordReplaceFilter({r"r'(foo)'": r"\2"})


@pytest.mark.parametrize("cls", [SkipWithKeywordsFilter, AllowWithKeywordsFilter])
def test_empty_keywords_rejected(cls):
    """An empty set would compile to a match-everything regex — fail fast instead."""
    with pytest.raises(ValueError):
        cls(set())


def test_skip_with_keywords_still_works():
    f = SkipWithKeywordsFilter({"spam"})
    action, _ = _process(f, make_message("this is spam"))
    assert action is FilterAction.DISCARD
    action, _ = _process(f, make_message("this is fine"))
    assert action is FilterAction.CONTINUE


def test_case_transfer_that_changes_length_keeps_entities_aligned():
    # "straße".upper() == "STRASSE": one char longer than the expanded
    # replacement, so the entity shift must use the case-transferred length.
    f = KeywordReplaceFilter({"foo": "straße"})
    msg = make_message("FOO tail", entities=[types.MessageEntityBold(offset=4, length=4)])
    _, res = _process(f, msg)
    assert res.message == "STRASSE tail"
    assert entity_text(res, res.entities[0]) == "tail"


_OLIMP_RULE = "r'\\bолимп(?:а|у|ом|е)?\\b'"  # as in both live configs


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Заходи в Олимп", FilterAction.DISCARD),
        ("Участники Олимпа уже тут", FilterAction.DISCARD),
        ("Встречаемся в олимпе", FilterAction.DISCARD),
        ("С ОЛИМПОМ на связи", FilterAction.DISCARD),
        ("Пишите Олимпу", FilterAction.DISCARD),
        ("Школьная олимпиада", FilterAction.CONTINUE),
        ("Олимпийский резерв", FilterAction.CONTINUE),
    ],
)
def test_olimp_rule_catches_case_forms_not_derived_words(text, expected):
    action, _ = _process(SkipWithKeywordsFilter({_OLIMP_RULE}), make_message(text))
    assert action is expected


@pytest.mark.parametrize("text, expected", [
    ("пишите @frmtribune", FilterAction.DISCARD),  # after a space
    ("@frmtribune — наш чат", FilterAction.DISCARD),  # at the start
    ("(@frmtribune)", FilterAction.DISCARD),
    ("пишите @frmtribune2", FilterAction.CONTINUE),  # another name
    ("пишите x@frmtribune", FilterAction.CONTINUE),  # inside a word
])
def test_a_plain_keyword_with_a_symbol_is_a_whole_word(text, expected):
    """``@name`` as a plain word used to need ``\\b`` before ``@`` — a word
    character — so it never matched after a space; it had to be an r'...'."""
    action, _ = _process(SkipWithKeywordsFilter({"@frmtribune"}), make_message(text))
    assert action == expected


@pytest.mark.parametrize("text, expected", [
    ("купите спам", FilterAction.DISCARD),
    ("спам!", FilterAction.DISCARD),
    ("спамер", FilterAction.CONTINUE),  # whole words only, as before
    ("антиспам", FilterAction.CONTINUE),
])
def test_a_plain_word_still_matches_whole_words_only(text, expected):
    action, _ = _process(SkipWithKeywordsFilter({"спам"}), make_message(text))
    assert action == expected


def test_a_plain_handle_is_replaced_after_a_space():
    f = KeywordReplaceFilter({"@old": "@new"})
    _, res = _process(f, make_message("пишите @old"))
    assert res.message == "пишите @new"


def test_a_plain_replacement_is_inserted_as_is():
    """``\\1`` / backslashes are a regex rule's business: a plain keyword's
    replacement is literal text (it used to be refused or reinterpreted)."""
    f = KeywordReplaceFilter({"path": r"c:\dir\1"})
    _, res = _process(f, make_message("the path here"))
    assert res.message == r"the c:\dir\1 here"


def test_a_keyword_with_an_emoji_outside_the_bmp_matches():
    """An emoji outside the BMP in a keyword matches, and the entities after
    it keep their UTF-16 offsets (🪞 is two units)."""
    f = KeywordReplaceFilter({"🪞зеркало": "копия"})
    msg = make_message("тут 🪞зеркало и ссылка")
    msg.entities = [types.MessageEntityBold(offset=16, length=6)]  # "ссылка", after the 🪞 (2 units)
    _, res = _process(f, msg)
    assert res.message == "тут копия и ссылка"
    assert entity_text(res, res.entities[0]) == "ссылка"


def test_case_transfer_on_a_letter_outside_the_bmp():
    """A letter outside the BMP (Deseret 𐐨 → 𐐀) has a case too."""
    f = KeywordReplaceFilter({"ab": "𐐨b"})
    _, res = _process(f, make_message("AB!"))
    assert res.message == "𐐀B!"


def test_a_regex_class_of_emoji_replaces_whole_emoji_only():
    """Regression: rules ran on the surrogate form, where ``[🔥💥]`` is a class
    of half-emoji — 😀 (same first half as 🔥) broke and the filter raised."""
    f = KeywordReplaceFilter({"r'[🔥💥]'": "X"})
    msg = make_message("😀 hi 🔥 end")
    msg.entities = [types.MessageEntityBold(offset=9, length=3)]  # "end", after 😀 and 🔥 (2 units each)
    _, res = _process(f, msg)
    assert res.message == "😀 hi X end"
    assert entity_text(res, res.entities[0]) == "end"


def test_a_regex_dot_takes_a_whole_emoji():
    """Regression: on the surrogate form ``.`` matched half of 😀 and the
    filter raised UnicodeDecodeError."""
    f = KeywordReplaceFilter({"r'hi.'": "X"})
    msg = make_message("hi😀 end")
    msg.entities = [types.MessageEntityBold(offset=5, length=3)]  # "end"
    _, res = _process(f, msg)
    assert res.message == "X end"
    assert entity_text(res, res.entities[0]) == "end"


@pytest.mark.parametrize("keyword", ["", "r''"])
def test_an_empty_keyword_is_refused(keyword):
    for make in (lambda: KeywordReplaceFilter({keyword: "x"}), lambda: SkipWithKeywordsFilter({keyword})):
        with pytest.raises(ValueError, match="empty keyword"):
            make()


def test_keywords_that_only_clash_together_are_a_value_error():
    with pytest.raises(ValueError, match="don't combine"):
        SkipWithKeywordsFilter({"r'(?P<x>a)'", "r'(?P<x>b)'"})
