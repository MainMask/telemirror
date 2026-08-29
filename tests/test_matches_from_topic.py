"""Topic routing extracted from new_message/new_album."""

import logging

from config import DirectionConfig
from telemirror.messagefilters import EmptyMessageFilter
from telemirror.mirroring import EventProcessor
from telemirror.storage import InMemoryDatabase
from tests.conftest import make_message, run


def _proc():
    return EventProcessor(
        chat_mapping={},
        database=run(InMemoryDatabase()),
        client=object(),
        logger=logging.getLogger("test"),
    )


def _cfg(from_topic_id):
    return DirectionConfig(
        disable_delete=False,
        disable_edit=False,
        filters=EmptyMessageFilter(),
        from_topic_id=from_topic_id,
    )


class ReplyTo:
    def __init__(self, forum_topic=False, top_id=None, msg_id=None):
        self.forum_topic = forum_topic
        self.reply_to_top_id = top_id
        self.reply_to_msg_id = msg_id


def test_not_topic_scoped_always_matches():
    p = _proc()
    m = make_message("hi")
    assert p._matches_from_topic(_cfg(None), m) is True


def test_general_topic_matches_non_reply():
    p = _proc()
    m = make_message("hi")
    m.reply_to = None
    assert p._matches_from_topic(_cfg(1), m) is True
    assert p._matches_from_topic(_cfg(7), m) is False


def test_forum_topic_uses_top_id_then_msg_id():
    p = _proc()
    m = make_message("hi")
    m.reply_to = ReplyTo(forum_topic=True, top_id=42, msg_id=99)
    assert p._matches_from_topic(_cfg(42), m) is True
    assert p._matches_from_topic(_cfg(99), m) is False

    m.reply_to = ReplyTo(forum_topic=True, top_id=None, msg_id=99)
    assert p._matches_from_topic(_cfg(99), m) is True


def test_reply_in_non_forum_is_general():
    p = _proc()
    m = make_message("hi")
    m.reply_to = ReplyTo(forum_topic=False, msg_id=5)
    assert p._matches_from_topic(_cfg(1), m) is True
    assert p._matches_from_topic(_cfg(5), m) is False
