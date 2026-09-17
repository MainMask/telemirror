"""Sign-off coverage for the URL-oriented filters (SkipUrlFilter,
SkipWithUrlFilter, UrlMessageFilter redaction) — matching logic that runs on
every message and depends on the previously-fixed UrlMatcher."""

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
