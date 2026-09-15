"""_restricted_content_blocks / _already_mirrored_skip / _resolve_reply_target:
the fan-out logic new_message and new_album share (extracted to remove the
~250-line duplication between them — see REVIEW.md)."""

import logging

from config import DirectionConfig
from telemirror.mirroring import EventProcessor
from telemirror.storage import InMemoryDatabase
from tests.conftest import run

SOURCE = -1001000000000
TARGET = -1002000000001


def _proc():
    return EventProcessor(
        chat_mapping={},
        database=run(InMemoryDatabase()),
        client=object(),
        logger=logging.getLogger("test.fanout"),
    )


class _FakeFilters:
    def __init__(self, restricted_content_allowed: bool):
        self.restricted_content_allowed = restricted_content_allowed

    async def process(self, entity, event_type):
        raise NotImplementedError


def _cfg(mode="copy", to_topic_id=None, restricted_content_allowed=True):
    return DirectionConfig(
        disable_delete=False,
        disable_edit=False,
        filters=_FakeFilters(restricted_content_allowed),
        mode=mode,
        to_topic_id=to_topic_id,
    )


def test_restricted_content_blocks_forward_mode():
    p = _proc()
    cfg = _cfg(mode="forward")
    assert p._restricted_content_blocks(cfg, True, SOURCE, TARGET) is True


def test_restricted_content_allows_when_source_not_restricted():
    p = _proc()
    cfg = _cfg(mode="forward")
    assert p._restricted_content_blocks(cfg, False, SOURCE, TARGET) is False


def test_restricted_content_allows_copy_with_reuploading_filter():
    p = _proc()
    cfg = _cfg(mode="copy", restricted_content_allowed=True)
    assert p._restricted_content_blocks(cfg, True, SOURCE, TARGET) is False


def test_already_mirrored_skip_single_route():
    p = _proc()
    skip = p._already_mirrored_skip(
        "[New message]", "link", TARGET, matching=[_cfg()], already_mirrored={TARGET}
    )
    assert skip is True


def test_already_mirrored_not_skipped_when_multi_topic_route():
    p = _proc()
    skip = p._already_mirrored_skip(
        "[New message]", "link", TARGET,
        matching=[_cfg(to_topic_id=1), _cfg(to_topic_id=2)],
        already_mirrored={TARGET},
    )
    assert skip is False


def test_resolve_reply_target_falls_back_to_topic_anchor():
    cfg = _cfg(to_topic_id=42)
    reply_to, reply_to_topic_id = EventProcessor._resolve_reply_target(
        cfg, reply_to_messages={}, outgoing_chat=TARGET
    )
    assert reply_to == 42
    assert reply_to_topic_id is None


def test_resolve_reply_target_chains_to_mirrored_parent_in_topic():
    cfg = _cfg(to_topic_id=42)
    reply_to, reply_to_topic_id = EventProcessor._resolve_reply_target(
        cfg, reply_to_messages={TARGET: 999}, outgoing_chat=TARGET
    )
    assert reply_to == 999
    assert reply_to_topic_id == 42


def test_resolve_reply_target_non_topic_target_uses_mirrored_parent():
    cfg = _cfg(to_topic_id=None)
    reply_to, reply_to_topic_id = EventProcessor._resolve_reply_target(
        cfg, reply_to_messages={TARGET: 999}, outgoing_chat=TARGET
    )
    assert reply_to == 999
    assert reply_to_topic_id is None
