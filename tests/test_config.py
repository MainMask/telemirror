import datetime

import pytest

from telemirror.config import (
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
    StripFooterFilter,
    WatermarkRemovalFilter,
)
from telemirror.directions import DirectionConfig, PastModeConfig
from tests.conftest import ONE_DIRECTION, import_config


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


def test_parse_chat_topic():
    """Shared by directions and broadcast_targets: plain id -> (id, None), a
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
    with pytest.raises(ValueError, match="StripFooterFilter"):
        _validate_forward_filters(StripFooterFilter(), "forward", "src->dst")


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
    (see telemirror.config's build loop) — a channel-scoped WatermarkRemovalFilter
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


def test_direction_level_filters_are_built_once_per_direction(tmp_path):
    """A direction with its own `filters:` must share ONE filter instance across
    all its source/target pairs — the same way `default_filters` is shared —
    or each pair gets its own ReuploadCache and the same media is downloaded
    and re-encoded once per target. Run in a subprocess: config builds
    CHAT_MAPPING at import time."""
    yaml_cfg = (
        "directions:\n"
        "  - from: [-1001, -1002]\n"
        "    to: [-1003, -1004]\n"
        "    filters:\n"
        "      - SkipWithKeywordsFilter:\n"
        "          keywords: [foo]\n"
    )
    probe = (
        "from telemirror.config import CHAT_MAPPING\n"
        "ids = {id(c.filters) for t in CHAT_MAPPING.values()"
        " for cs in t.values() for c in cs}\n"
        "print(len(ids))\n"
    )
    out = import_config(tmp_path, probe, yaml_cfg)
    assert out.returncode == 0, out.stderr[-500:]
    assert out.stdout.strip() == "1"


def test_broadcast_targets_take_chat_and_topic(tmp_path):
    out = import_config(tmp_path, (
        "from telemirror.config import CHAT_MAPPING as m\n"
        "print(sorted((t, c.to_topic_id) for t, cs in m[-1009].items() for c in cs))"
    ), ONE_DIRECTION + "broadcast_channel: -1009\nbroadcast_targets: [-1002, '-1003#5']\n")
    assert out.returncode == 0, out.stderr[-500:]
    assert out.stdout.strip() == "[(-1003, 5), (-1002, None)]"


def test_dedup_hours_project_wide_and_per_direction(tmp_path):
    yaml_cfg = (
        "dedup_hours: 24\n"
        "directions:\n"
        "  - from: [-1001]\n    to: [-1002]\n"
        "  - from: [-1003]\n    to: [-1004]\n    dedup_hours: 0\n"
    )
    probe = ("from telemirror.config import CHAT_MAPPING as m; "
             "print(m[-1001][-1002][0].dedup_hours, m[-1003][-1004][0].dedup_hours)")
    out = import_config(tmp_path, probe, yaml_cfg)
    assert out.returncode == 0, out.stderr
    assert out.stdout.split() == ["24.0", "0.0"]


@pytest.mark.parametrize("text", ["", "# only a comment\n", "directions:\n", "- a list\n", "mode: copy\n"])
def test_a_config_without_a_directions_list_is_a_clear_error(tmp_path, text):
    out = import_config(tmp_path, "import telemirror.config", text)
    assert out.returncode != 0 and "expected a mapping with a 'directions:' list" in out.stderr


def test_an_empty_directions_list_loads(tmp_path):
    out = import_config(tmp_path, "import telemirror.config", "directions: []\n")
    assert out.returncode == 0, out.stderr


def test_two_filters_in_one_list_item_are_refused(tmp_path):
    """A mis-indented next filter lands in the previous one's item: refused,
    not silently dropped."""
    text = ("filters:\n  - SkipUrlFilter: {}\n    EmptyMessageFilter: {}\n" + ONE_DIRECTION)
    out = import_config(tmp_path, "import telemirror.config", text)
    assert out.returncode != 0 and "one filter per list item, got SkipUrlFilter, EmptyMessageFilter" in out.stderr


def test_negative_dedup_hours_is_refused(tmp_path):
    """Regression: a negative value written by hand (the panel allows 0..720)
    was truthy — it turned the check on with a cutoff in the future (nothing
    ever a repeat) and pruned every fingerprint of the project each hour."""
    out = import_config(tmp_path, "import telemirror.config", ONE_DIRECTION + "dedup_hours: -1\n")
    assert out.returncode != 0
    assert "dedup_hours must be 0 or more" in out.stderr


@pytest.mark.parametrize("value", [".nan", ".inf", "24h", "true"])
def test_dedup_hours_must_be_a_number_of_hours(tmp_path, value):
    """``.nan`` is truthy and never < 0: it passed, and every post's check then
    failed (a warning to the admins each time). «24h» failed with a bare
    ValueError that didn't say which direction; «true» passed as 1 hour."""
    out = import_config(tmp_path, "import telemirror.config", ONE_DIRECTION + f"dedup_hours: {value}\n")
    assert out.returncode != 0
    assert "->" in out.stderr and "dedup_hours must be 0 or more" in out.stderr


@pytest.mark.parametrize("text, where, key", [
    ("disable_edits: true\n" + ONE_DIRECTION, "mirror.config.yml", "disable_edits"),
    ("directions:\n  - from: [-1001]\n    to: [-1002]\n    disable_edits: true\n",
     "direction from [-1001]", "disable_edits"),
    ("directions:\n  - from: [-1001]\n    to: [-1002]\n    past_mode: {last_n: 5, lastn: 9}\n",
     "past_mode", "lastn"),
])
def test_an_unknown_key_is_refused(tmp_path, text, where, key):
    """A typo (or a key the mirror was never taught) used to be silently
    ignored — the mirror then ran with the default instead."""
    out = import_config(tmp_path, "import telemirror.config", text)
    assert out.returncode != 0
    assert f"{where}: unknown key(s) {key}" in out.stderr


@pytest.mark.parametrize("text, said", [
    ("directions:\n  - -1001\n", "a direction is a mapping with from: and to:, got -1001"),
    ("directions:\n  - from: [-1001]\n    to: [-1002]\n    past_mode: true\n", "past_mode: expected a mapping"),
    ("directions:\n  - from: [-1001]\n    to: [-1002]\n    mode: [copy]\n", "mode must be 'copy' or 'forward'"),
])
def test_a_misshapen_entry_says_what_is_wrong(tmp_path, text, said):
    """Regression: a bare AttributeError / TypeError instead of what to fix."""
    out = import_config(tmp_path, "import telemirror.config", text)
    assert out.returncode != 0
    assert said in out.stderr


def test_every_known_key_loads(tmp_path):
    text = (
        "mode: copy\ndisable_delete: false\ndisable_edit: false\n"
        "fallback_link_url: https://t.me/x\ndedup_hours: 0\nfilters: []\n"
        "broadcast_channel: -1009\nbroadcast_targets: [-1002]\n"
        "directions:\n  - from: [-1001]\n    to: [-1002]\n    mode: copy\n"
        "    disable_delete: false\n    disable_edit: false\n    send_delay: 0\n"
        "    fallback_link_url: https://t.me/x\n    dedup_hours: 0\n    filters: []\n"
        "    past_mode: {last_n: 5, send_delay: 1, drip: {posts: 1, minutes: 1}}\n"
    )
    out = import_config(tmp_path, "import telemirror.config", text)
    assert out.returncode == 0, out.stderr[-500:]


@pytest.mark.parametrize("line, error", [
    ('disable_edit: "false"', "-1001->-1002: disable_edit must be true or false, got 'false'"),
    ('disable_delete: 1', "-1001->-1002: disable_delete must be true or false, got 1"),
    ('send_delay: "1"', "-1001->-1002: send_delay must be a number ≥ 0, got '1'"),
    ('send_delay: .inf', "-1001->-1002: send_delay must be a number ≥ 0, got inf"),
    ('past_mode: {last_n: "5"}', "past_mode: last_n must be a whole number ≥ 1, got '5'"),
    ('past_mode: {last_n: 0}', "past_mode: last_n must be a whole number ≥ 1, got 0"),
    ('past_mode: {full_history: "no"}', "past_mode: full_history must be true or false, got 'no'"),
    ('past_mode: {last_n: 5, send_delay: -1}', "past_mode: send_delay must be a number ≥ 0, got -1"),
])
def test_a_value_of_the_wrong_type_is_refused(tmp_path, line, error):
    """A quoted value passed: «"false"» is truthy — edits turned off, the
    opposite of what was written; «"1"» failed only once the mirror used it."""
    out = import_config(tmp_path, "import telemirror.config", ONE_DIRECTION + f"    {line}\n")
    assert out.returncode != 0
    assert error in out.stderr


def test_values_of_the_right_type_load(tmp_path):
    text = ONE_DIRECTION + (
        "    disable_edit: no\n    disable_delete: true\n    send_delay: 2\n"
        "    past_mode: {full_history: true, send_delay: 0.5}\n"
    )
    probe = ("from telemirror.config import CHAT_MAPPING as m; c = m[-1001][-1002][0]; "
             "print(c.disable_edit, c.disable_delete, c.send_delay, c.past_mode.full_history)")
    out = import_config(tmp_path, probe, text)
    assert out.returncode == 0, out.stderr[-500:]
    assert out.stdout.split() == ["False", "True", "2", "True"]


@pytest.mark.parametrize("filter_yaml, error", [
    ("SkipWithUrlFilter: {blacklist: ads.com}", "filters: SkipWithUrlFilter.blacklist must be Set[str], got 'ads.com'"),
    ("SkipWithKeywordsFilter: {keywords: spam}", "filters: SkipWithKeywordsFilter.keywords must be set[str], got 'spam'"),
    ('SkipUrlFilter: {skip_mention: "false"}', "filters: SkipUrlFilter.skip_mention must be bool, got 'false'"),
    ("DocumentFilenameFilter: {suffix: 5}", "filters: DocumentFilenameFilter.suffix must be str, got 5"),
    ("UrlMessageFilter: {placeholder: 123}", "filters: UrlMessageFilter.placeholder must be str, got 123"),
    ('StripFooterFilter: {max_lines: "3"}', "filters: StripFooterFilter.max_lines must be int, got '3'"),
])
def test_a_filter_arg_of_the_wrong_type_is_refused(tmp_path, filter_yaml, error):
    """«blacklist: ads.com» became the set of its letters, «"false"» a truthy
    switch, «suffix: 5» failed only on the first document."""
    out = import_config(tmp_path, "import telemirror.config", f"filters:\n  - {filter_yaml}\n" + ONE_DIRECTION)
    assert out.returncode != 0
    assert error in out.stderr


def test_filter_args_of_the_right_type_load(tmp_path):
    text = (
        "filters:\n"
        "  - SkipWithUrlFilter: {blacklist: [ads.com]}\n"  # a list where a set is declared
        "  - UrlMessageFilter: {filter_mention: [some_user], whitelist: null}\n"  # bool | set, Optional
        "  - StripFooterFilter: {max_lines: 3}\n"
        "  - WatermarkRemovalFilter: {remove_watermark: false}\n"  # **config: Any — not checked here
    ) + ONE_DIRECTION
    out = import_config(tmp_path, "import telemirror.config", text)
    assert out.returncode == 0, out.stderr[-500:]


def test_every_default_the_panel_writes_fits_the_filter():
    """The panel's catalog and the filters' declared types can't drift apart:
    what the panel writes by default, the mirror accepts."""
    import inspect

    from bot.filtercatalog import FILTER_ARGS
    from telemirror import messagefilters
    from telemirror.config import _fits

    for name, args in FILTER_ARGS.items():
        params = inspect.signature(getattr(messagefilters, name).__init__).parameters
        for arg, _kind, default in args:
            if default is not None and arg in params:
                assert _fits(params[arg].annotation, default), (name, arg, default)


def test_a_bad_fallback_link_is_refused(tmp_path):
    out = import_config(tmp_path, "import telemirror.config", "fallback_link_url: 123\n" + ONE_DIRECTION)
    assert out.returncode != 0
    assert "-1001->-1002: fallback_link_url must be a link, got 123" in out.stderr


def test_a_past_mode_error_names_its_direction(tmp_path):
    text = ONE_DIRECTION + "    past_mode: {last_n: 5, drip: {posts: 0, minutes: 1}}\n"
    out = import_config(tmp_path, "import telemirror.config", text)
    assert out.returncode != 0
    assert "-1001->-1002: past_mode.drip.posts: expected a whole number ≥ 1, got 0" in out.stderr
