import datetime

import pytest

from config import (
    DirectionConfig,
    PastModeConfig,
    _channel_id,
    _parse_chat_topic,
    _validate_forward_filters,
    _validate_mode,
    _validate_watermark_filter_order,
)
from telemirror.messagefilters import (
    CompositeMessageFilter,
    DocumentFilenameFilter,
    EmptyMessageFilter,
    KeywordReplaceFilter,
    RestrictSavingContentBypassFilter,
    SkipWithKeywordsFilter,
    WatermarkRemovalFilter,
)


@pytest.mark.parametrize("unset", [None, "", "0", "  ", " 0 "])
def test_channel_id_treats_blank_and_zero_as_unset(unset):
    assert _channel_id(unset, "BROADCAST_CHANNEL") is None


def test_channel_id_parses_marked_id():
    assert _channel_id("-1001234", "X") == -1001234
    assert _channel_id(-1001234, "X") == -1001234


def test_channel_id_rejects_non_numeric_with_context():
    with pytest.raises(ValueError, match="BROADCAST_CHANNEL"):
        _channel_id("not-a-number", "BROADCAST_CHANNEL")


def test_past_mode_requires_exactly_one_strategy():
    PastModeConfig(full_history=True)
    PastModeConfig(last_n=100)
    PastModeConfig(since_date=datetime.datetime(2024, 1, 1))

    with pytest.raises(ValueError):
        PastModeConfig()  # none
    with pytest.raises(ValueError):
        PastModeConfig(last_n=5, full_history=True)  # two


def test_past_mode_since_date_coercion():
    """YAML yields datetime/date for an unquoted value, str for a quoted one."""
    expected = datetime.datetime(2024, 1, 1, 0, 0)
    for raw in (
        datetime.datetime(2024, 1, 1),
        datetime.date(2024, 1, 1),
        "2024-01-01T00:00:00",
        "2024-01-01",
    ):
        cfg = PastModeConfig(since_date=raw)
        assert isinstance(cfg.since_date, datetime.datetime)
        assert cfg.since_date == expected


def test_parse_chat_topic_shared_by_yaml_and_env_branches():
    """Extracted from duplicated YAML/env parsing (Phase 4 DRY cleanup) — both
    branches must keep exactly this behavior: plain id -> (id, None), a
    '#'-suffixed string -> (id, topic_id), and a YAML-native int passes
    through unchanged (no '#' possible on a non-string)."""
    assert _parse_chat_topic("-1001234") == (-1001234, None)
    assert _parse_chat_topic("-1001234#5") == (-1001234, 5)
    assert _parse_chat_topic(-1001234) == (-1001234, None)  # YAML bare int


def test_validate_mode_accepts_copy_and_forward():
    assert _validate_mode("copy", "src->dst") == "copy"
    assert _validate_mode("forward", "src->dst") == "forward"


def test_validate_mode_rejects_bad_value_with_context():
    """A YAML typo (e.g. `mode: Copy`) must fail fast at load time instead of
    silently mixing mirroring.py's `== "forward"`/`== "copy"` branches."""
    with pytest.raises(ValueError, match="src->dst"):
        _validate_mode("Copy", "src->dst")


def test_validate_forward_filters_allows_decision_only_filter():
    _validate_forward_filters(SkipWithKeywordsFilter(keywords={"x"}), "forward", "src->dst")
    _validate_forward_filters(EmptyMessageFilter(), "forward", "src->dst")


def test_validate_forward_filters_ignores_copy_mode():
    # mode: copy can carry any filter, content-mutating or not.
    _validate_forward_filters(KeywordReplaceFilter(keywords={"a": "b"}), "copy", "src->dst")


def test_validate_forward_filters_rejects_content_mutating_filter():
    with pytest.raises(ValueError, match="src->dst"):
        _validate_forward_filters(
            KeywordReplaceFilter(keywords={"a": "b"}), "forward", "src->dst"
        )
    with pytest.raises(ValueError, match="WatermarkRemovalFilter"):
        _validate_forward_filters(WatermarkRemovalFilter(), "forward", "src->dst")


def test_validate_forward_filters_checks_inside_composite():
    composite = CompositeMessageFilter(
        [SkipWithKeywordsFilter(keywords={"x"}), KeywordReplaceFilter(keywords={"a": "b"})]
    )
    with pytest.raises(ValueError, match="KeywordReplaceFilter"):
        _validate_forward_filters(composite, "forward", "src->dst")


def test_validate_watermark_filter_order_rejects_restrict_before_watermark():
    composite = CompositeMessageFilter(
        [RestrictSavingContentBypassFilter(), WatermarkRemovalFilter()]
    )
    with pytest.raises(ValueError, match="src->dst"):
        _validate_watermark_filter_order(composite, "src->dst")


def test_validate_watermark_filter_order_rejects_document_filename_before_watermark():
    """DocumentFilenameFilter also re-uploads media (into an upload handle)
    whenever a rename actually fires — the same hazard as
    RestrictSavingContentBypassFilter for a following WatermarkRemovalFilter."""
    composite = CompositeMessageFilter(
        [DocumentFilenameFilter(), WatermarkRemovalFilter()]
    )
    with pytest.raises(ValueError, match="src->dst"):
        _validate_watermark_filter_order(composite, "src->dst")


def test_validate_watermark_filter_order_names_the_first_offending_filter():
    composite = CompositeMessageFilter([
        RestrictSavingContentBypassFilter(),
        DocumentFilenameFilter(),
        WatermarkRemovalFilter(),
    ])
    with pytest.raises(ValueError, match="RestrictSavingContentBypassFilter"):
        _validate_watermark_filter_order(composite, "src->dst")


def test_validate_watermark_filter_order_rejects_consuming_filter_between_two_watermark_instances():
    """channels= lets WatermarkRemovalFilter appear more than once in one
    chain (different watermark config per channel group) — a consuming
    filter placed between two instances must still be caught, not just one
    placed before the first."""
    composite = CompositeMessageFilter([
        WatermarkRemovalFilter(channels=[1]),
        RestrictSavingContentBypassFilter(),
        WatermarkRemovalFilter(channels=[2]),
    ])
    with pytest.raises(ValueError, match="src->dst"):
        _validate_watermark_filter_order(composite, "src->dst")


def test_validate_watermark_filter_order_allows_watermark_before_restrict():
    composite = CompositeMessageFilter(
        [WatermarkRemovalFilter(), RestrictSavingContentBypassFilter()]
    )
    _validate_watermark_filter_order(composite, "src->dst")


def test_validate_watermark_filter_order_allows_watermark_alone():
    _validate_watermark_filter_order(WatermarkRemovalFilter(), "src->dst")
    _validate_watermark_filter_order(EmptyMessageFilter(), "src->dst")


def test_direction_config_defaults():
    d = DirectionConfig(
        disable_delete=False, disable_edit=False, filters=EmptyMessageFilter()
    )
    assert d.mode == "copy"
    assert d.from_topic_id is None
    assert d.send_delay == 0.0
    assert "mode: copy" in repr(d)
