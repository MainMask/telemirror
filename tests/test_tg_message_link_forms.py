"""Pass 22, third review: every form of a t.me message link is rewritten.

`_TG_MSG_LINK_RE` used to accept only `https?://t.me/c/<chat>/<msg>` and
`https?://t.me/<username>/<msg>`. A link to a message inside a forum topic
(`t.me/c/<chat>/<topic>/<msg>`), a bare `t.me/…` that Telegram linkifies
without a scheme, and the `telegram.me` / `www.t.me` hosts were left
untouched — the mirror kept the donor's private link and `fallback_link_url`
was never applied.
"""

import logging

import pytest
from telethon import errors, utils
from telethon.tl import types

from config import DirectionConfig
from telemirror.messagefilters import (
    EmptyMessageFilter,
    FilterAction,
    SkipWithUrlFilter,
)
from telemirror.mirroring import EventProcessor
from telemirror.misc.links import private_message_link
from telemirror.storage import InMemoryDatabase, MirrorMessage
from tests.conftest import entity_text, make_message, run

SOURCE = -1001000000000
TARGET = -1002000000001
REF_RAW = 2000000009
REF = utils.get_peer_id(types.PeerChannel(REF_RAW))
FALLBACK = "https://t.me/fallback"
MIRROR_LINK = private_message_link(TARGET, 500)


class _Client:
    async def get_entity(self, username):
        assert username.lower() == "donor"
        return types.PeerChannel(REF_RAW)


def _processor(db):
    cfg = DirectionConfig(
        disable_delete=False, disable_edit=False,
        filters=EmptyMessageFilter(), fallback_link_url=FALLBACK,
    )
    return EventProcessor(
        chat_mapping={SOURCE: {TARGET: [cfg]}, REF: {TARGET: [cfg]}},
        database=db,
        client=_Client(),
        logger=logging.getLogger("test.linkforms"),
    )


def _rewrite_text_url(url, mirrored=True):
    db = run(InMemoryDatabase())
    if mirrored:
        run(db.insert(MirrorMessage(5, REF, 500, TARGET)))
    msg = make_message(
        "link", entities=[types.MessageEntityTextUrl(offset=0, length=4, url=url)]
    )
    run(_processor(db)._rewrite_links(msg, SOURCE, TARGET, FALLBACK, {}, None))
    return msg.entities[0].url


@pytest.mark.parametrize(
    "url",
    [
        f"https://t.me/c/{REF_RAW}/3/5",  # private, inside forum topic 3
        f"https://t.me/c/{REF_RAW}/3/5?single",
        "https://t.me/donor/3/5",  # public, inside forum topic 3
        f"t.me/c/{REF_RAW}/5",  # no scheme
        f"https://telegram.me/c/{REF_RAW}/5",
        f"https://www.t.me/c/{REF_RAW}/5",
    ],
)
def test_message_link_form_is_rewritten_to_the_mirror(url):
    assert _rewrite_text_url(url) == MIRROR_LINK


def test_topic_link_without_a_mirror_in_the_target_uses_the_fallback():
    assert _rewrite_text_url(f"https://t.me/c/{REF_RAW}/3/5", mirrored=False) == FALLBACK


@pytest.mark.parametrize(
    "url",
    [
        "https://t.me/s/donor/5",  # web preview of a channel, not a message link
        "https://t.me/addstickers/pack",
        "https://t.me/donor",
        f"https://example.com/c/{REF_RAW}/5",
        f"https://t.me/c/{REF_RAW}/1/2/5",
    ],
)
def test_non_message_links_are_left_alone(url):
    assert _rewrite_text_url(url) == url


def test_bare_url_entity_text_is_replaced_and_later_entities_shift():
    db = run(InMemoryDatabase())
    run(db.insert(MirrorMessage(5, REF, 500, TARGET)))
    bare = f"t.me/c/{REF_RAW}/3/5"
    text = f"see {bare} now"
    msg = make_message(
        text,
        entities=[
            types.MessageEntityUrl(offset=4, length=len(bare)),
            types.MessageEntityBold(offset=5 + len(bare), length=3),
        ],
    )

    run(_processor(db)._rewrite_links(msg, SOURCE, TARGET, FALLBACK, {}, None))

    assert msg.message == f"see {MIRROR_LINK} now"
    assert entity_text(msg, msg.entities[0]) == MIRROR_LINK
    assert entity_text(msg, msg.entities[1]) == "now"


def test_unresolvable_username_link_is_left_for_the_blacklist():
    """Links were rewritten before the filters, and a message link whose
    username failed to resolve (a deleted/renamed channel) got
    `fallback_link_url` — so `SkipWithUrlFilter` never saw a blacklisted
    `t.me/<old-brand>/<id>` and the promo post was mirrored. Now such a link is
    left untouched, like one to a channel that resolves but isn't mirrored."""
    class _GoneClient:
        async def get_entity(self, username):
            raise errors.UsernameNotOccupiedError(request=None)

    proc = _processor(run(InMemoryDatabase()))
    proc._client = _GoneClient()
    url = "https://t.me/managerfrm/12"
    msg = make_message(
        "promo", entities=[types.MessageEntityTextUrl(offset=0, length=5, url=url)]
    )

    run(proc._rewrite_links(msg, SOURCE, TARGET, FALLBACK, {}, None))
    action, _ = run(
        SkipWithUrlFilter(blacklist={"t.me/managerfrm"}).process(msg, None)
    )

    assert msg.entities[0].url == url
    assert action is FilterAction.DISCARD


def _flood():
    return errors.FloodWaitError(request=None, capture=900)


@pytest.mark.parametrize(
    "failure, expected",
    [
        (None, MIRROR_LINK),  # resolves: rewritten to the mirror
        # The username doesn't exist (deleted/renamed channel): untouched, so
        # SkipWithUrlFilter can still see a blacklisted one.
        (lambda: errors.UsernameNotOccupiedError(request=None), "https://t.me/donor/5"),
        (lambda: ValueError('No user has "donor" as username'), "https://t.me/donor/5"),
        # Transient: it may be a mirrored donor — hide its link behind the fallback.
        (_flood, FALLBACK),
        (lambda: ConnectionError("reset"), FALLBACK),
        # Telethon collapses exhausted server-error retries into this ValueError.
        (lambda: ValueError("Request was unsuccessful 5 time(s)"), FALLBACK),
    ],
)
def test_username_resolution_failure_kinds(failure, expected):
    """Pass 22, sixth review: after the fifth review every failed resolution
    left the link untouched, so a transient failure (a long FloodWait, a
    network error) on a live, mirrored donor showed `t.me/<donor>/<id>` in the
    mirror. Only a username that doesn't exist is left untouched now."""

    class _Client:
        async def get_entity(self, username):
            if failure is not None:
                raise failure()
            return types.PeerChannel(REF_RAW)

    db = run(InMemoryDatabase())
    run(db.insert(MirrorMessage(5, REF, 500, TARGET)))
    proc = _processor(db)
    proc._client = _Client()
    msg = make_message(
        "link",
        entities=[types.MessageEntityTextUrl(offset=0, length=4, url="https://t.me/donor/5")],
    )

    run(proc._rewrite_links(msg, SOURCE, TARGET, FALLBACK, {}, None))

    assert msg.entities[0].url == expected


def test_blacklisted_channel_outside_the_config_stays_blocked():
    """A retired donor (dropped from the config, its binding_id rows left
    behind) that is blacklisted: its link must stay untouched so
    SkipWithUrlFilter drops the post. Giving it the fallback because the post
    has mirror rows (a reverted Pass 23 change) sent the promo post."""
    old_raw = 3000000007
    old = utils.get_peer_id(types.PeerChannel(old_raw))

    class _RetiredClient:
        async def get_entity(self, username):
            return types.PeerChannel(old_raw)

    db = run(InMemoryDatabase())
    run(db.insert(MirrorMessage(12, old, 777, -1003000000008)))
    proc = _processor(db)
    proc._client = _RetiredClient()
    url = "https://t.me/openfrm/12"
    msg = make_message(
        "promo", entities=[types.MessageEntityTextUrl(offset=0, length=5, url=url)]
    )
    run(proc._rewrite_links(msg, SOURCE, TARGET, FALLBACK, {}, None))

    assert msg.entities[0].url == url
    action, _ = run(SkipWithUrlFilter({"t.me/openfrm"}).process(msg, None))
    assert action is FilterAction.DISCARD
