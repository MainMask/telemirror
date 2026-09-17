"""`reply_to_messages` in `new_message`/`new_album` must not silently
collapse two mirrors of the same source message that share a
`mirror_channel` but live in different topics of that channel (`binding_id`
has no topic column, so the two rows are indistinguishable by DB lookup
alone). Picking either one risks reply-chaining to a mirror living in the
wrong topic; the safe fallback is to skip reply-chaining for that target
(post as a plain topic message instead of guessing). See REVIEW.md."""

import logging

from telethon.tl import types

import telemirror.mirroring as mirroring
from config import DirectionConfig
from telemirror.messagefilters import EmptyMessageFilter
from telemirror.mirroring import EventProcessor
from telemirror.storage import InMemoryDatabase, MirrorMessage
from tests.conftest import make_message, run

SOURCE = -1001000000000
TARGET = -1002000000001


def _cfg(from_topic_id, to_topic_id):
    return DirectionConfig(
        disable_delete=False,
        disable_edit=False,
        filters=EmptyMessageFilter(),
        from_topic_id=from_topic_id,
        to_topic_id=to_topic_id,
    )


def test_ambiguous_reply_target_across_topics_is_not_guessed(monkeypatch):
    """TARGET is reached by two topic-scoped configs that both match the
    same source topic (a catch-all `from_topic_id=None` config plus a
    topic-specific one) — the same source message was therefore already
    mirrored into TARGET twice, under two different mirror_ids living in two
    different destination topics."""
    db = run(InMemoryDatabase())

    # Seed as if the replied-to message was already mirrored into TARGET via
    # both configs (topic 10's copy and topic 20's copy).
    run(
        db.insert_batch(
            [
                MirrorMessage(
                    original_id=1, original_channel=SOURCE,
                    mirror_id=111, mirror_channel=TARGET,
                ),
                MirrorMessage(
                    original_id=1, original_channel=SOURCE,
                    mirror_id=222, mirror_channel=TARGET,
                ),
            ]
        )
    )

    calls = []

    async def fake_send_message(
        client, entity, message, reply_to=None, reply_to_topic_id=None, **kw
    ):
        calls.append((reply_to, reply_to_topic_id))
        return types.Message(id=999, peer_id=types.PeerChannel(1), message="x")

    monkeypatch.setattr(mirroring, "send_message", fake_send_message)

    proc = EventProcessor(
        chat_mapping={SOURCE: {TARGET: [_cfg(None, 10), _cfg(5, 20)]}},
        database=db,
        client=object(),
        logger=logging.getLogger("test.reply_ambiguity"),
    )

    child = make_message("reply", channel_id=1000)
    child.id = 2
    child.reply_to = types.MessageReplyHeader(
        forum_topic=True, reply_to_top_id=5, reply_to_msg_id=1
    )

    run(proc.new_message(SOURCE, child, "link"))

    # Both configs match (from_topic_id=None catches everything,
    # from_topic_id=5 matches this message's topic), so both fire. Neither
    # ambiguous mirror_id (111, 222) may be used as a reply target — doing
    # so would reply-chain into whichever topic that mirror_id actually
    # lives in, which may not match the topic being posted into. The safe
    # fallback is a plain topic post: reply_to == each config's own topic
    # anchor, no reply_to_topic_id (matches the pre-existing "no known
    # mirror to reply to" path).
    assert set(calls) == {(10, None), (20, None)}


def test_reply_target_resolved_when_mirror_topic_is_known(monkeypatch):
    """Same TARGET/config setup as above, but the seeded rows carry their
    real `mirror_topic_id` (as new inserts record post-fix) — the reply must
    now correctly reply-chain to each config's own topic's mirror instead of
    falling back to a plain topic post."""
    db = run(InMemoryDatabase())

    run(
        db.insert_batch(
            [
                MirrorMessage(
                    original_id=1, original_channel=SOURCE,
                    mirror_id=111, mirror_channel=TARGET, mirror_topic_id=10,
                ),
                MirrorMessage(
                    original_id=1, original_channel=SOURCE,
                    mirror_id=222, mirror_channel=TARGET, mirror_topic_id=20,
                ),
            ]
        )
    )

    calls = []

    async def fake_send_message(
        client, entity, message, reply_to=None, reply_to_topic_id=None, **kw
    ):
        calls.append((reply_to, reply_to_topic_id))
        return types.Message(id=999, peer_id=types.PeerChannel(1), message="x")

    monkeypatch.setattr(mirroring, "send_message", fake_send_message)

    proc = EventProcessor(
        chat_mapping={SOURCE: {TARGET: [_cfg(None, 10), _cfg(5, 20)]}},
        database=db,
        client=object(),
        logger=logging.getLogger("test.reply_ambiguity"),
    )

    child = make_message("reply", channel_id=1000)
    child.id = 2
    child.reply_to = types.MessageReplyHeader(
        forum_topic=True, reply_to_top_id=5, reply_to_msg_id=1
    )

    run(proc.new_message(SOURCE, child, "link"))

    # Each config now correctly reply-chains to its own topic's mirror
    # instead of both falling back to a plain topic post.
    assert set(calls) == {(111, 10), (222, 20)}
