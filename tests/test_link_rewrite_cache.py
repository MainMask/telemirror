"""Pass 10 (perf): link resolution in the fan-out must be done once per event,
not once per target/config.

``EventProcessor._rewrite_links`` used to re-run ``get_messages`` (a DB round-trip)
and ``get_entity`` (a network round-trip) for every t.me link for every fan-out
target, even though the result depends only on ``(url, fallback_link_url)``.
"""

import logging
from types import SimpleNamespace

from telethon import utils
from telethon.tl import types

import telemirror.mirroring as mirroring
from config import DirectionConfig
from telemirror.messagefilters import EmptyMessageFilter
from telemirror.mirroring import EventProcessor
from telemirror.misc.links import private_message_link
from telemirror.storage import InMemoryDatabase, MirrorMessage
from tests.conftest import make_message, run

SOURCE = -1001000000000
TARGET_A = -1002000000001
TARGET_B = -1002000000002
REF_RAW = 2000000009
REF = utils.get_peer_id(types.PeerChannel(REF_RAW))
REF_MIRROR = -1002000000077


def _cfg():
    return DirectionConfig(
        disable_delete=False, disable_edit=False, filters=EmptyMessageFilter()
    )


class _CountingDB(InMemoryDatabase):
    def __init__(self):
        super().__init__()
        self.get_messages_calls = 0

    async def get_messages(self, original_id, original_channel):
        # count only link-resolution lookups (against the referenced channel),
        # not the unrelated per-message dedup guard in new_message
        if original_channel == REF:
            self.get_messages_calls += 1
        return await super().get_messages(original_id, original_channel)


def test_link_resolution_is_cached_across_fanout(monkeypatch):
    db = run(_CountingDB())
    run(db.insert(MirrorMessage(5, REF, 500, REF_MIRROR)))

    async def fake_send_message(client, entity, message, **kw):
        return types.Message(id=1, peer_id=types.PeerChannel(1), message="x")

    monkeypatch.setattr(mirroring, "send_message", fake_send_message)

    proc = EventProcessor(
        chat_mapping={
            SOURCE: {TARGET_A: [_cfg()], TARGET_B: [_cfg()]},
            REF: {REF_MIRROR: [_cfg()]},
        },
        database=db,
        client=object(),
        logger=logging.getLogger("test.linkcache"),
    )

    msg = make_message(
        "link",
        entities=[
            types.MessageEntityTextUrl(
                offset=0, length=4, url=f"https://t.me/c/{REF_RAW}/5"
            )
        ],
        channel_id=1000,
    )
    msg._chat = SimpleNamespace(noforwards=False)

    run(proc.new_message(SOURCE, msg, "link"))

    # 2 fan-out targets, but the referenced link is resolved once.
    assert db.get_messages_calls == 1


def test_ambiguous_topic_mirrors_are_not_guessed():
    """A referenced message mirrored twice into the same channel (reached via
    two topic-scoped configs — binding_id has no topic column) must not be
    rewritten to an arbitrary one of those mirror ids: the fallback is used
    instead, same "leave out rather than guess" rule as _reply_target_mirrors.
    """
    db = run(InMemoryDatabase())
    run(db.insert(MirrorMessage(5, REF, 500, REF_MIRROR)))
    run(db.insert(MirrorMessage(5, REF, 501, REF_MIRROR)))

    proc = EventProcessor(
        chat_mapping={REF: {REF_MIRROR: [_cfg()]}},
        database=db,
        client=object(),
        logger=logging.getLogger("test.linkcache"),
    )
    msg = make_message("link", channel_id=1000)

    result = run(
        proc._try_rewrite_tg_link(
            f"https://t.me/c/{REF_RAW}/5", SOURCE, msg, REF_MIRROR,
            "https://fallback.example/5",
        )
    )

    assert result == "https://fallback.example/5"


def test_topic_scoped_mirror_is_resolved_when_mirror_topic_is_known():
    """Same two-mirror setup as `test_ambiguous_topic_mirrors_are_not_guessed`,
    but the rows carry their real `mirror_topic_id` (as new inserts record
    post-fix) — the link must now be rewritten to the mirror matching the
    requested `to_topic_id` instead of falling back."""
    db = run(InMemoryDatabase())
    run(db.insert(MirrorMessage(5, REF, 500, REF_MIRROR, mirror_topic_id=10)))
    run(db.insert(MirrorMessage(5, REF, 501, REF_MIRROR, mirror_topic_id=20)))

    proc = EventProcessor(
        chat_mapping={REF: {REF_MIRROR: [_cfg()]}},
        database=db,
        client=object(),
        logger=logging.getLogger("test.linkcache"),
    )
    msg = make_message("link", channel_id=1000)

    result = run(
        proc._try_rewrite_tg_link(
            f"https://t.me/c/{REF_RAW}/5", SOURCE, msg, REF_MIRROR,
            "https://fallback.example/5", to_topic_id=20,
        )
    )

    assert result == private_message_link(REF_MIRROR, 501)


def test_legacy_untagged_mirror_resolved_for_a_topic_scoped_request():
    """A referenced message with only a pre-migration mirror row
    (`mirror_topic_id=None` — inserted before that column existed, no
    backfill) must still resolve for a topic-scoped `to_topic_id` request,
    or every already-mirrored pre-migration link would fall back to
    `fallback_link_url` the moment a topic-scoped direction rewrites it."""
    db = run(InMemoryDatabase())
    run(db.insert(MirrorMessage(5, REF, 500, REF_MIRROR)))  # mirror_topic_id=None

    proc = EventProcessor(
        chat_mapping={REF: {REF_MIRROR: [_cfg()]}},
        database=db,
        client=object(),
        logger=logging.getLogger("test.linkcache"),
    )
    msg = make_message("link", channel_id=1000)

    result = run(
        proc._try_rewrite_tg_link(
            f"https://t.me/c/{REF_RAW}/5", SOURCE, msg, REF_MIRROR,
            "https://fallback.example/5", to_topic_id=7,
        )
    )

    assert result == private_message_link(REF_MIRROR, 500)


def test_each_fanout_target_gets_its_own_mirror_link():
    """A referenced message mirrored into two *different* target channels
    (REF_MIRROR_A, REF_MIRROR_B — each unambiguous on its own) must have its
    link rewritten to the mirror in the *same* channel the current copy is
    being sent to, not to whichever target's mirror was resolved first and
    then reused for every other target via link_cache.
    """
    ref_mirror_a = REF_MIRROR
    ref_mirror_b = -1002000000088
    db = run(InMemoryDatabase())
    run(db.insert(MirrorMessage(5, REF, 500, ref_mirror_a)))
    run(db.insert(MirrorMessage(5, REF, 600, ref_mirror_b)))

    proc = EventProcessor(
        chat_mapping={REF: {ref_mirror_a: [_cfg()], ref_mirror_b: [_cfg()]}},
        database=db,
        client=object(),
        logger=logging.getLogger("test.linkcache"),
    )
    msg = make_message("link", channel_id=1000)
    url = f"https://t.me/c/{REF_RAW}/5"
    link_cache: dict = {}

    result_a = run(
        proc._try_rewrite_tg_link(url, SOURCE, msg, ref_mirror_a, link_cache=link_cache)
    )
    result_b = run(
        proc._try_rewrite_tg_link(url, SOURCE, msg, ref_mirror_b, link_cache=link_cache)
    )

    assert result_a == private_message_link(ref_mirror_a, 500)
    assert result_b == private_message_link(ref_mirror_b, 600)


def test_username_resolution_is_cached_on_the_processor():
    calls = []

    class FakeClient:
        async def get_entity(self, username):
            calls.append(username)
            return types.PeerChannel(REF_RAW)

    proc = EventProcessor(
        chat_mapping={}, database=object(), client=FakeClient(),
        logger=logging.getLogger("test.linkcache"),
    )
    msg = make_message("x", channel_id=1000)
    msg._chat = SimpleNamespace(username=None)

    first = run(proc._resolve_username_to_channel_id("somechan", SOURCE, msg))
    second = run(proc._resolve_username_to_channel_id("SomeChan", SOURCE, msg))

    assert first == second
    assert calls == ["somechan"]  # second call served from cache
