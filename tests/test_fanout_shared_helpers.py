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


def _cfg(mode="copy", to_topic_id=None, restricted_content_allowed=True, from_topic_id=None):
    return DirectionConfig(
        disable_delete=False,
        disable_edit=False,
        filters=_FakeFilters(restricted_content_allowed),
        mode=mode,
        from_topic_id=from_topic_id,
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


def test_already_mirrored_skip_when_this_config_topic_already_mirrored():
    p = _proc()
    cfg = _cfg(to_topic_id=1)
    skip = p._already_mirrored_skip(
        "[New message]", "link", TARGET, cfg, already_mirrored={(TARGET, None, 1)}
    )
    assert skip is True


def test_already_mirrored_not_skipped_for_a_different_sibling_topic():
    """Two configs route to the same TARGET channel via different topics —
    only the topic actually already mirrored is skipped, the other still
    sends (this used to be an all-or-nothing "don't skip either" bandaid;
    with mirror_topic_id recorded, each config's own topic is now judged
    independently)."""
    p = _proc()
    already_mirrored = {(TARGET, None, 1)}
    assert p._already_mirrored_skip(
        "[New message]", "link", TARGET, _cfg(to_topic_id=1), already_mirrored
    ) is True
    assert p._already_mirrored_skip(
        "[New message]", "link", TARGET, _cfg(to_topic_id=2), already_mirrored
    ) is False


def test_already_mirrored_skip_falls_back_to_legacy_untagged_row():
    """A row inserted before `mirror_topic_id`/`source_topic_id` existed
    (both stay `None` forever for it — there's no backfill) must still
    count as "already mirrored" for a topic-scoped config, or every
    pre-migration mirror would look unmirrored to the dedup guard and get
    silently re-sent as a duplicate the first time a topic-scoped direction
    checks it after this ships."""
    p = _proc()
    cfg = _cfg(to_topic_id=5)
    skip = p._already_mirrored_skip(
        "[New message]", "link", TARGET, cfg, already_mirrored={(TARGET, None, None)}
    )
    assert skip is True


def test_already_mirrored_skip_disambiguates_via_source_topic_when_destination_collides():
    """Two configs share to_topic_id=None (a non-forum target) but differ in
    from_topic_id — mirror_topic_id alone can't tell their rows apart, so a
    row produced by one config must not cause the other's still-genuinely-
    unsent copy to be skipped."""
    p = _proc()
    general = _cfg(to_topic_id=None, from_topic_id=None)
    scoped = _cfg(to_topic_id=None, from_topic_id=20)
    already_mirrored = {(TARGET, 20, None)}
    assert p._already_mirrored_skip(
        "[New message]", "link", TARGET, scoped, already_mirrored
    ) is True
    assert p._already_mirrored_skip(
        "[New message]", "link", TARGET, general, already_mirrored
    ) is False


def test_already_mirrored_skip_legacy_fallback_is_consumed_by_first_config():
    """A lone ambiguous legacy row (no from/to topic recorded) can honestly
    justify skipping at most one config — it's genuinely unknown which
    config produced it, but it can't have been more than one. Once one
    config claims it via the fallback, a different config checking the same
    already_mirrored set must not also treat it as its own evidence."""
    p = _proc()
    already_mirrored = {(TARGET, None, None)}
    cfg_a = _cfg(to_topic_id=None, from_topic_id=5)
    cfg_b = _cfg(to_topic_id=None, from_topic_id=6)
    assert p._already_mirrored_skip(
        "[New message]", "link", TARGET, cfg_a, already_mirrored
    ) is True
    assert p._already_mirrored_skip(
        "[New message]", "link", TARGET, cfg_b, already_mirrored
    ) is False


def test_config_for_topic_exact_match_is_authoritative_even_if_disabled():
    """An exact-topic match must win even though a sibling topic's config
    for the same channel isn't disabled — this is exactly the bug being
    fixed: a protected topic's row must never inherit a sibling topic's
    permissive setting just because it comes first in the channel's config
    list. Used by edit_message/delete_message."""
    protected = DirectionConfig(
        disable_delete=True, disable_edit=True, filters=_FakeFilters(True), to_topic_id=1
    )
    open_cfg = DirectionConfig(
        disable_delete=False, disable_edit=False, filters=_FakeFilters(True), to_topic_id=2
    )
    resolved = EventProcessor._config_for_topic(
        [open_cfg, protected], None, 1, lambda c: c.disable_delete
    )
    assert resolved is protected
    assert resolved.disable_delete is True


def test_config_for_topic_falls_back_to_first_non_disabled_when_no_exact_match():
    """A legacy row (`mirror_topic_id=None`) or one whose topic-scoped
    direction was since removed from config: falls back to this project's
    pre-`mirror_topic_id` behavior — first non-disabled config in the
    list."""
    disabled = DirectionConfig(
        disable_delete=True, disable_edit=True, filters=_FakeFilters(True), to_topic_id=1
    )
    enabled = DirectionConfig(
        disable_delete=False, disable_edit=False, filters=_FakeFilters(True), to_topic_id=2
    )
    resolved = EventProcessor._config_for_topic(
        [disabled, enabled], None, 99, lambda c: c.disable_delete
    )
    assert resolved is enabled


def test_config_for_topic_returns_none_when_no_match_and_all_disabled():
    disabled = DirectionConfig(
        disable_delete=True, disable_edit=True, filters=_FakeFilters(True), to_topic_id=1
    )
    assert EventProcessor._config_for_topic(
        [disabled], None, 99, lambda c: c.disable_delete
    ) is None


def test_config_for_topic_disambiguates_via_source_topic_when_destination_collides():
    """Two configs route to the same non-forum TARGET (to_topic_id=None for
    both) but differ in from_topic_id — mirror_topic_id alone can't tell
    them apart, so a row's own source_topic_id (the config's from_topic_id)
    must be matched too, or the first config in the list always wins
    regardless of which one actually produced the row."""
    general = DirectionConfig(
        disable_delete=True, disable_edit=True, filters=_FakeFilters(True),
        from_topic_id=None, to_topic_id=None,
    )
    scoped = DirectionConfig(
        disable_delete=False, disable_edit=False, filters=_FakeFilters(True),
        from_topic_id=20, to_topic_id=None,
    )
    assert EventProcessor._config_for_topic(
        [general, scoped], 20, None, lambda c: c.disable_delete
    ) is scoped
    assert EventProcessor._config_for_topic(
        [general, scoped], None, None, lambda c: c.disable_delete
    ) is general


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
        cfg, reply_to_messages={(TARGET, 42): 999}, outgoing_chat=TARGET
    )
    assert reply_to == 999
    assert reply_to_topic_id == 42


def test_resolve_reply_target_chains_to_legacy_untagged_parent():
    """Same migration-compatibility fallback as
    `test_already_mirrored_skip_falls_back_to_legacy_untagged_row`, for
    reply-chaining: a pre-migration parent row (`mirror_topic_id=None`)
    must still be found for a topic-scoped config."""
    cfg = _cfg(to_topic_id=42)
    reply_to, reply_to_topic_id = EventProcessor._resolve_reply_target(
        cfg, reply_to_messages={(TARGET, None): 999}, outgoing_chat=TARGET
    )
    assert reply_to == 999
    assert reply_to_topic_id == 42


def test_resolve_reply_target_non_topic_target_uses_mirrored_parent():
    cfg = _cfg(to_topic_id=None)
    reply_to, reply_to_topic_id = EventProcessor._resolve_reply_target(
        cfg, reply_to_messages={(TARGET, None): 999}, outgoing_chat=TARGET
    )
    assert reply_to == 999
    assert reply_to_topic_id is None
