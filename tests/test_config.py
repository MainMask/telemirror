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
        _validate_watermark_filter_order(composite, 1, "src->dst")


def test_validate_watermark_filter_order_rejects_document_filename_before_watermark():
    """DocumentFilenameFilter also re-uploads media (into an upload handle)
    whenever a rename actually fires — the same hazard as
    RestrictSavingContentBypassFilter for a following WatermarkRemovalFilter."""
    composite = CompositeMessageFilter(
        [DocumentFilenameFilter(), WatermarkRemovalFilter()]
    )
    with pytest.raises(ValueError, match="src->dst"):
        _validate_watermark_filter_order(composite, 1, "src->dst")


def test_validate_watermark_filter_order_names_the_first_offending_filter():
    composite = CompositeMessageFilter([
        RestrictSavingContentBypassFilter(),
        DocumentFilenameFilter(),
        WatermarkRemovalFilter(),
    ])
    with pytest.raises(ValueError, match="RestrictSavingContentBypassFilter"):
        _validate_watermark_filter_order(composite, 1, "src->dst")


def test_validate_watermark_filter_order_rejects_consuming_filter_between_two_watermark_instances():
    """channels= lets WatermarkRemovalFilter appear more than once in one
    chain (different watermark config per channel group) — a consuming
    filter placed between two instances must still be caught for a source
    the SECOND instance actually applies to, not just one placed before the
    first."""
    composite = CompositeMessageFilter([
        WatermarkRemovalFilter(channels=[1]),
        RestrictSavingContentBypassFilter(),
        WatermarkRemovalFilter(channels=[2]),
    ])
    with pytest.raises(ValueError, match="src->dst"):
        _validate_watermark_filter_order(composite, 2, "src->dst")


def test_validate_watermark_filter_order_allows_a_source_outside_the_later_instances_scope():
    """The same chain as above is NOT a hazard for source 1: its watermarking
    already completed via the FIRST instance (channels=[1]) before the
    consuming filter ran, and the second, channels=[2]-scoped instance never
    processes source 1's messages at all — so the consuming filter sitting
    before it is irrelevant for this source."""
    composite = CompositeMessageFilter([
        WatermarkRemovalFilter(channels=[1]),
        RestrictSavingContentBypassFilter(),
        WatermarkRemovalFilter(channels=[2]),
    ])
    _validate_watermark_filter_order(composite, 1, "src->dst")


def test_validate_watermark_filter_order_allows_watermark_before_restrict():
    composite = CompositeMessageFilter(
        [WatermarkRemovalFilter(), RestrictSavingContentBypassFilter()]
    )
    _validate_watermark_filter_order(composite, 1, "src->dst")


def test_validate_watermark_filter_order_allows_watermark_alone():
    _validate_watermark_filter_order(WatermarkRemovalFilter(), 1, "src->dst")
    _validate_watermark_filter_order(EmptyMessageFilter(), 1, "src->dst")


def test_validate_watermark_filter_order_rejects_in_scope_source_after_consuming_filter():
    """A channel-scoped WatermarkRemovalFilter is still a real hazard for a
    source it actually processes."""
    composite = CompositeMessageFilter(
        [RestrictSavingContentBypassFilter(), WatermarkRemovalFilter(channels=[1])]
    )
    with pytest.raises(ValueError, match="src->dst"):
        _validate_watermark_filter_order(composite, 1, "src->dst")


def test_validate_watermark_filter_order_allows_out_of_scope_source_after_consuming_filter():
    """A multi-source direction reuses the same filter list for every source
    (see config.py's build loop) — a channel-scoped WatermarkRemovalFilter
    that never processes THIS source is a no-op for it at runtime
    (watermarkfilter.py's `_process_message`), so a consuming filter before
    it is not a hazard for this source, regardless of filter order."""
    composite = CompositeMessageFilter(
        [RestrictSavingContentBypassFilter(), WatermarkRemovalFilter(channels=[1])]
    )
    _validate_watermark_filter_order(composite, 2, "src->dst")


def test_direction_config_defaults():
    d = DirectionConfig(
        disable_delete=False, disable_edit=False, filters=EmptyMessageFilter()
    )
    assert d.mode == "copy"
    assert d.from_topic_id is None
    assert d.send_delay == 0.0
    assert "mode: copy" in repr(d)


def test_direction_level_filters_are_built_once_per_direction():
    """A direction with its own `filters:` must share ONE filter instance across
    all its source/target pairs — the same way `default_filters` is shared —
    or each pair gets its own ReuploadCache and the same media is downloaded
    and re-encoded once per target. Run in a subprocess: config.py builds
    CHAT_MAPPING at import time, and reloading it here would redefine
    DirectionConfig under every other test."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    yaml_cfg = (
        "directions:\n"
        "  - from: [-1001, -1002]\n"
        "    to: [-1003, -1004]\n"
        "    filters:\n"
        "      - SkipWithKeywordsFilter:\n"
        "          keywords: [foo]\n"
    )
    probe = (
        "from config import CHAT_MAPPING\n"
        "ids = {id(c.filters) for t in CHAT_MAPPING.values()"
        " for cs in t.values() for c in cs}\n"
        "print(len(ids))\n"
    )
    env = {**os.environ, "YAML_CONFIG_ENV": yaml_cfg}
    out = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=Path(__file__).resolve().parent.parent,
        env=env, capture_output=True, text=True, check=True,
    )
    assert out.stdout.strip() == "1"
