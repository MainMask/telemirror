import datetime

import pytest

from config import DirectionConfig, PastModeConfig, _channel_id, _parse_chat_topic
from telemirror.messagefilters import EmptyMessageFilter


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


def test_direction_config_defaults():
    d = DirectionConfig(
        disable_delete=False, disable_edit=False, filters=EmptyMessageFilter()
    )
    assert d.mode == "copy"
    assert d.from_topic_id is None
    assert d.send_delay == 0.0
    assert "mode: copy" in repr(d)
