"""Sign-off coverage for the URL-oriented filters (SkipUrlFilter,
SkipWithUrlFilter, UrlMessageFilter redaction) — matching logic that runs on
every message and depends on the previously-fixed UrlMatcher."""

import pytest
from telethon import events
from telethon.tl import types

from telemirror.messagefilters.base import FilterAction
from telemirror.messagefilters.messagefilters import (
    SkipUrlFilter,
    SkipWithUrlFilter,
    UrlMessageFilter,
)
from tests.conftest import make_message, run


def _process(f, message):
    return run(f._process_message(message, events.NewMessage.Event))


def test_skip_url_filter_discards_on_bare_url_entity():
    msg = make_message(
        "see example.com", entities=[types.MessageEntityUrl(offset=4, length=11)]
    )
    action, _ = _process(SkipUrlFilter(), msg)
    assert action is FilterAction.DISCARD


def test_skip_url_filter_keeps_plain_text():
    action, _ = _process(SkipUrlFilter(), make_message("no links here"))
    assert action is FilterAction.CONTINUE


def test_skip_url_filter_mention_toggle():
    msg = make_message("hi @chan", entities=[types.MessageEntityMention(offset=3, length=5)])
    assert _process(SkipUrlFilter(skip_mention=True), msg)[0] is FilterAction.DISCARD
    assert _process(SkipUrlFilter(skip_mention=False), msg)[0] is FilterAction.CONTINUE


def test_skip_with_url_filter_prefix_match_on_text_url():
    msg = make_message(
        "click", entities=[types.MessageEntityTextUrl(
            offset=0, length=5, url="https://t.me/spam/42"
        )]
    )
    assert _process(SkipWithUrlFilter({"t.me/spam"}), msg)[0] is FilterAction.DISCARD
    assert _process(SkipWithUrlFilter({"t.me/other"}), msg)[0] is FilterAction.CONTINUE


def test_skip_with_url_filter_matches_mention_from_direct_tme_entry():
    msg = make_message("hi @spam", entities=[types.MessageEntityMention(offset=3, length=5)])
    assert _process(SkipWithUrlFilter({"t.me/spam"}), msg)[0] is FilterAction.DISCARD


def test_url_message_filter_redacts_blacklisted_bare_url():
    msg = make_message(
        "go t.me/bad now", entities=[types.MessageEntityUrl(offset=3, length=8)]
    )
    _, res = _process(UrlMessageFilter(blacklist={"t.me"}), msg)
    assert res.message == "go *** now"


def test_url_message_filter_mention_true_does_not_mangle_plain_hyperlinks():
    """`filter_mention=True` is documented as filtering @-mentions
    (MessageEntityMention); it must not also swallow every ordinary inline
    hyperlink (MessageEntityTextUrl) just because `_match_mention` returns the
    bare bool unconditionally for that entity kind too. A non-matching
    blacklist isolates this from the separate (pre-existing, correct)
    "drop a blacklisted TextUrl's link" branch — an *empty* blacklist means
    "everything is blacklisted" by `UrlMatcher.match()`'s own contract, which
    would confound the assertion."""
    msg = make_message(
        "Read the full report here",
        entities=[
            types.MessageEntityTextUrl(
                offset=9, length=11, url="https://legit-news.example.com/report"
            )
        ],
    )
    f = UrlMessageFilter(blacklist={"other-domain.example"}, filter_mention=True)
    _, res = _process(f, msg)
    assert res.message == "Read the full report here"
    assert len(res.entities) == 1


def test_url_message_filter_keeps_whitelisted_url():
    msg = make_message(
        "go example.com now", entities=[types.MessageEntityUrl(offset=3, length=11)]
    )
    _, res = _process(
        UrlMessageFilter(blacklist=set(), whitelist={"example.com"}), msg
    )
    assert res.message == "go example.com now"


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://telegram.me/godolympbot", FilterAction.DISCARD),
        ("telegram.dog/GodOlympBot", FilterAction.DISCARD),
        ("https://www.t.me/godolympbot?start=1", FilterAction.DISCARD),
        ("tg://resolve?domain=godolympbot&start=x", FilterAction.DISCARD),
        ("TG://resolve?domain=GodOlympBot", FilterAction.DISCARD),
        ("https://telegram.me/godolympbotX", FilterAction.CONTINUE),
        ("tg://resolve?domain=other", FilterAction.CONTINUE),
        ("https://nottelegram.me/godolympbot", FilterAction.CONTINUE),
    ],
)
def test_skip_with_url_filter_matches_telegram_link_aliases(url, expected):
    """telegram.me / telegram.dog / www.t.me and tg://resolve deep links reach
    the same chat as t.me — a hidden link in any of these forms must not slip
    past a t.me/… blacklist entry."""
    msg = make_message("click", entities=[types.MessageEntityTextUrl(0, 5, url)])
    assert _process(SkipWithUrlFilter({"t.me/godolympbot"}), msg)[0] is expected


@pytest.mark.parametrize(
    "url, expected",
    [
        ("tg://resolve?start=x&domain=godolympbot", FilterAction.DISCARD),
        ("tg://resolve?domain=godolympbot#frag", FilterAction.DISCARD),
        ("https://t.me/s/openfrm", FilterAction.DISCARD),
        ("https://t.me/s/openfrm/123", FilterAction.DISCARD),
        ("https://openfrm.t.me", FilterAction.DISCARD),
        ("https://openfrm.t.me/123", FilterAction.DISCARD),
        ("https://t.me/iv?url=x&rhash=y", FilterAction.CONTINUE),
        ("https://x.nott.me/openfrm", FilterAction.CONTINUE),
        ("https://openfrmx.t.me", FilterAction.CONTINUE),
        ("tg://resolve?start=x", FilterAction.CONTINUE),
        ("https://t.me/s/other", FilterAction.CONTINUE),
    ],
)
def test_skip_with_url_filter_folds_all_chat_link_forms(url, expected):
    """Every link form that opens the same chat as t.me/<name> — tg://resolve
    with parameters in any order or a fragment, the t.me/s/ web preview, and
    the <name>.t.me subdomain — must hit a t.me/<name> blacklist entry."""
    msg = make_message("click", entities=[types.MessageEntityTextUrl(0, 5, url)])
    f = SkipWithUrlFilter({"t.me/godolympbot", "t.me/openfrm"})
    assert _process(f, msg)[0] is expected


def _chat_link_forms(name, tail):
    forms = [
        f"t.me/{name}{tail}",
        f"https://t.me/{name}{tail}",
        f"HTTP://www.t.me/{name}{tail}",
        f"telegram.me/{name}{tail}",
        f"https://telegram.dog/{name}{tail}",
        f"https://t.me/s/{name}{tail}",
        f"https://{name}.t.me{tail}",
    ]
    if tail in ("", "#x"):
        forms.append(f"tg://resolve?domain={name}{tail}")
    return forms


@pytest.mark.parametrize(
    "tail", ["", "/", "/42", "/42/", "?start=1", "/7?single", "#x", "/42#x", "?start=1#x"]
)
@pytest.mark.parametrize("name", ["godolympbot", "bot_2x"])
def test_skip_with_url_filter_every_form_normalizes_like_t_me(name, tail):
    """Property check over every link form that opens the same chat: each must
    normalize exactly like t.me/<name> with the same tail (query or fragment
    directly after a subdomain host included), normalization must be
    idempotent, and a blacklist entry written in an alias form must still
    match every form without catching a longer name."""
    normalize = SkipWithUrlFilter._normalize
    canon = normalize(f"t.me/{name}{tail}")
    f = SkipWithUrlFilter({f"telegram.me/{name}"})
    for url in _chat_link_forms(name, tail):
        assert normalize(url) == canon, url
        assert normalize(normalize(url)) == normalize(url), url
        assert f._matches(url), url
    assert not f._matches(f"https://t.me/{name}x")
