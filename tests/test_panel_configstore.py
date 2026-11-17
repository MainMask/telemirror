"""Panel config writes: comments survive, refusals leave the file untouched,
and every candidate is validated by config.py itself."""

from pathlib import Path

import pytest
import yaml

from telemirror.panel import configstore as cs
from telemirror.misc.jsession import TDESKTOP_APP, save_jsession
from telemirror.projects import Project
from tests.conftest import run

EXAMPLE = Path(__file__).resolve().parent.parent / ".configs" / "mirror.config.yml-example"

PYYAML_STYLE = """\
# generated header — must survive
disable_edit: true
directions:
- from:
  - -1001234567890
  to:
  - -1009876543210
  past_mode:
    full_history: true
- from:
  - '-1001111111111#1'
  to:
  - '-1002222222222#5'
"""


def _project(tmp_path, text):
    path = tmp_path / "mirror.config.yml"
    path.write_text(text, encoding="utf-8")
    session = tmp_path / "s.jsession"
    if not session.exists():
        me = type("Me", (), {"first_name": "T", "last_name": None, "id": 1, "phone": "7", "username": None})
        save_jsession(str(session), "1AAAA", me, TDESKTOP_APP)
    return Project("t", "Тест", "🧪", str(session), str(path), 8123)


async def _ok(_project, _text):
    return None


def _store(validator=_ok):
    return cs.ConfigStore(validator=validator)


# ── input validation ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw, ref",
    [
        ("-1001234567890", "-1001234567890"),
        ("  -1001234567890#4 ", "-1001234567890#4"),
        ("−1001234567890", "-1001234567890"),  # unicode minus from a phone keyboard
    ],
)
def test_normalize_chat_ref_accepts(raw, ref):
    assert cs.normalize_chat_ref(raw) == ref


@pytest.mark.parametrize(
    "raw",
    ["", "abc", "1001234567890", "-1234567890", "-100123", "-1001234567890#0",
     "-1001234567890#", "-1001234567890#x", "@channel", "-1001234567890#4#5"],
)
def test_normalize_chat_ref_rejects(raw):
    with pytest.raises(cs.ConfigError) as e:
        cs.normalize_chat_ref(raw)
    assert e.value.code == "bad_ref"


def test_parse_chat_refs_dedups_and_splits():
    assert cs.parse_chat_refs("-1001111111111, -1002222222222#3\n-1001111111111") == [
        "-1001111111111",
        "-1002222222222#3",
    ]
    with pytest.raises(cs.ConfigError):
        cs.parse_chat_refs(" , ")


# ── mutations ───────────────────────────────────────────────────────────────


def test_add_direction_round_trip_keeps_comments_and_sets(tmp_path):
    project = _project(tmp_path, EXAMPLE.read_text(encoding="utf-8"))
    before = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))

    def mutate(data):
        cs.add_direction(data, ["-1005555555555"], ["-1006666666666#2", "-1007777777777"], "copy", True)

    run(_store().update(project, mutate))

    text = project.config_path.read_text(encoding="utf-8")
    after = yaml.safe_load(text)
    assert after["directions"][:-1] == before["directions"]
    assert after["directions"][-1] == {
        "from": [-1005555555555],
        "to": ["-1006666666666#2", -1007777777777],
        "past_mode": {"full_history": True},
    }
    assert after["filters"] == before["filters"]  # !!set values intact
    assert "# (Optional) Admin broadcast channel" in text  # comments survive
    assert "#   ? t.me/c/        # prefix" in text
    assert project.config_path.with_suffix(".yml.bak").read_text(encoding="utf-8") == EXAMPLE.read_text(
        encoding="utf-8"
    )


def test_pyyaml_style_file_keeps_its_indentation(tmp_path):
    project = _project(tmp_path, PYYAML_STYLE)
    snap = cs.load(project)
    fp = cs.fingerprint(cs.directions(snap.data)[0])
    run(_store().update(project, lambda d: cs.toggle_direction_flag(d, 0, fp, "disable_edit")))
    text = project.config_path.read_text(encoding="utf-8")
    assert text.startswith("# generated header — must survive\n")
    assert "- from:\n  - -1001234567890\n" in text  # indentless lists kept
    data = yaml.safe_load(text)
    assert data["directions"][0]["disable_edit"] is False  # inherited true → toggled off
    assert data["directions"][1]["from"] == ["-1001111111111#1"]


def test_delete_and_toggle_global(tmp_path):
    project = _project(tmp_path, PYYAML_STYLE)
    fp = cs.fingerprint(cs.directions(cs.load(project).data)[0])
    run(_store().update(project, lambda d: cs.delete_direction(d, 0, fp)))
    run(_store().update(project, lambda d: cs.toggle_global(d, "disable_edit")))
    run(_store().update(project, lambda d: cs.toggle_global(d, "mode")))
    data = yaml.safe_load(project.config_path.read_text(encoding="utf-8"))
    assert len(data["directions"]) == 1
    assert data["disable_edit"] is False
    assert data["mode"] == "forward"


def test_stale_fingerprint_refused(tmp_path):
    project = _project(tmp_path, PYYAML_STYLE)
    with pytest.raises(cs.ConfigError) as e:
        run(_store().update(project, lambda d: cs.delete_direction(d, 0, "deadbeef")))
    assert e.value.code == "stale"
    assert project.config_path.read_text(encoding="utf-8") == PYYAML_STYLE
    assert not project.config_path.with_suffix(".yml.bak").exists()


@pytest.mark.parametrize(
    "sources, targets, code",
    [
        (["-1001234567890"], ["-1009876543210"], "duplicate"),
        (["-1001234567890"], ["-1001234567890#3"], "self_loop"),
    ],
)
def test_add_direction_refusals(tmp_path, sources, targets, code):
    project = _project(tmp_path, PYYAML_STYLE)
    with pytest.raises(cs.ConfigError) as e:
        run(_store().update(project, lambda d: cs.add_direction(d, sources, targets, "copy", False)))
    assert e.value.code == code
    assert project.config_path.read_text(encoding="utf-8") == PYYAML_STYLE


def test_validator_failure_leaves_file_untouched(tmp_path):
    project = _project(tmp_path, PYYAML_STYLE)

    async def reject(_project, _text):
        return "ValueError: nope"

    with pytest.raises(cs.ConfigError) as e:
        run(_store(reject).update(project, lambda d: cs.toggle_global(d, "mode")))
    assert (e.value.code, e.value.detail) == ("invalid", "ValueError: nope")
    assert project.config_path.read_text(encoding="utf-8") == PYYAML_STYLE


def test_manual_edit_during_write_refused(tmp_path):
    project = _project(tmp_path, PYYAML_STYLE)

    async def edit_meanwhile(_project, _text):
        project.config_path.write_text(PYYAML_STYLE + "# hand edit\n", encoding="utf-8")
        return None

    with pytest.raises(cs.ConfigError) as e:
        run(_store(edit_meanwhile).update(project, lambda d: cs.toggle_global(d, "mode")))
    assert e.value.code == "changed_on_disk"
    assert project.config_path.read_text(encoding="utf-8").endswith("# hand edit\n")


def test_read_only_when_the_file_is_missing(tmp_path):
    project = _project(tmp_path, PYYAML_STYLE)
    assert cs.read_only_reason(project) is None
    project.config_path.unlink()
    assert cs.read_only_reason(project) == "missing"
    with pytest.raises(cs.ConfigError) as e:
        run(_store().update(project, lambda d: cs.toggle_global(d, "mode")))
    assert e.value.code == "read_only"


def test_fingerprint_is_stable_and_content_sensitive():
    a = {"from": [-1001], "to": [-1002], "filters": [{"SkipWithKeywordsFilter": {"keywords": {"b", "a"}}}]}
    b = {"from": [-1001], "to": [-1002], "filters": [{"SkipWithKeywordsFilter": {"keywords": {"a", "b"}}}]}
    assert cs.fingerprint(a) == cs.fingerprint(b)
    assert cs.fingerprint(a) != cs.fingerprint({**a, "mode": "forward"})
    assert len(cs.fingerprint(a)) == 8


# ── the real validator: config.py in a subprocess ───────────────────────────


def test_validate_with_config_py(tmp_path):
    project = _project(tmp_path, "")
    ok = "directions:\n  - from: [-1001234567890]\n    to: [-1009876543210]\n"
    bad = (
        "filters:\n  - UrlMessageFilter:\n      blacklist: !!set\n        ? t.me\n"
        "mode: forward\n" + ok
    )
    assert run(cs.validate(project, ok)) is None
    error = run(cs.validate(project, bad))
    assert error is not None and "mode 'forward'" in error


def test_example_config_validates(tmp_path):
    project = _project(tmp_path, "")
    assert run(cs.validate(project, EXAMPLE.read_text(encoding="utf-8"))) is None


# ── direction / global edits ────────────────────────────────────────────────

WITH_FILTERS = """\
# comment
filters:
  - SkipWithKeywordsFilter:
      keywords: !!set
        ? stop   # keep me
        ? "123"
  - UrlMessageFilter:
      blacklist: !!set
        ? t.me
  - ForwardFormatFilter:
      format: "{message_text}"
directions:
  - from: [-1001111111111]
    to: [-1002222222222]
    filters:
      - AllowWithKeywordsFilter:
          keywords: [a, b]
  - from: [-1003333333333]
    to: [-1004444444444]
    past_mode:
      last_n: 5
      send_delay: 2.0
"""


def _fp(project, i):
    return cs.fingerprint(cs.directions(cs.load(project).data)[i])


def test_set_direction_refs_and_mode(tmp_path):
    project = _project(tmp_path, WITH_FILTERS)
    fp = _fp(project, 0)
    run(_store().update(project, lambda d: cs.set_direction_refs(d, 0, fp, "to", ["-1005555555555#2"])))
    run(_store().update(project, lambda d: cs.toggle_direction_mode(d, 0, _fp(project, 0))))
    data = yaml.safe_load(project.config_path.read_text(encoding="utf-8"))
    assert data["directions"][0]["to"] == ["-1005555555555#2"]
    assert data["directions"][0]["mode"] == "forward"


def test_set_direction_refs_refuses_duplicate_of_other_direction(tmp_path):
    project = _project(tmp_path, WITH_FILTERS)
    fp = _fp(project, 1)
    run(_store().update(project, lambda d: cs.set_direction_refs(d, 1, fp, "to", ["-1002222222222"])))
    with pytest.raises(cs.ConfigError) as e:
        run(_store().update(project, lambda d: cs.set_direction_refs(d, 1, _fp(project, 1), "from", ["-1001111111111"])))
    assert e.value.code == "duplicate"
    # its own pair doesn't clash with itself
    run(_store().update(project, lambda d: cs.set_direction_refs(d, 0, _fp(project, 0), "to", ["-1002222222222"])))


def test_set_direction_values(tmp_path):
    project = _project(tmp_path, WITH_FILTERS)
    run(_store().update(project, lambda d: cs.set_direction_value(d, 1, _fp(project, 1), "past_mode", {"full_history": True})))
    run(_store().update(project, lambda d: cs.set_direction_value(d, 0, _fp(project, 0), "send_delay", 1.5)))
    data = yaml.safe_load(project.config_path.read_text(encoding="utf-8"))
    assert data["directions"][1]["past_mode"] == {"full_history": True, "send_delay": 2.0}  # replay delay kept
    assert data["directions"][0]["send_delay"] == 1.5
    run(_store().update(project, lambda d: cs.set_direction_value(d, 0, _fp(project, 0), "send_delay", None)))
    run(_store().update(project, lambda d: cs.set_direction_value(d, 1, _fp(project, 1), "past_mode", None)))
    data = yaml.safe_load(project.config_path.read_text(encoding="utf-8"))
    assert "send_delay" not in data["directions"][0] and "past_mode" not in data["directions"][1]


def test_set_global_values(tmp_path):
    project = _project(tmp_path, WITH_FILTERS)
    run(_store().update(project, lambda d: cs.set_global_value(d, "tech_channel", -1009999999999)))
    run(_store().update(project, lambda d: cs.set_global_value(d, "broadcast_targets", [-1001111111111, "-1002222222222#3"])))
    run(_store().update(project, lambda d: cs.set_global_value(d, "fallback_link_url", "https://t.me/x")))
    data = yaml.safe_load(project.config_path.read_text(encoding="utf-8"))
    assert data["tech_channel"] == -1009999999999
    assert data["broadcast_targets"] == [-1001111111111, "-1002222222222#3"]
    assert data["fallback_link_url"] == "https://t.me/x"
    run(_store().update(project, lambda d: cs.set_global_value(d, "tech_channel", None)))
    assert "tech_channel" not in yaml.safe_load(project.config_path.read_text(encoding="utf-8"))
    with pytest.raises(ValueError):
        cs.set_global_value({}, "api_hash", "x")


# ── filter items ────────────────────────────────────────────────────────────


def test_filter_items_add_remove_keep_types(tmp_path):
    project = _project(tmp_path, WITH_FILTERS)
    data = cs.load(project).data
    entries = cs.filters_of(data, -1)
    assert [cs.editable_args(e) for e in entries] == [("keywords",), ("blacklist", "whitelist"), ()]
    assert cs.filter_items(entries[0], "keywords") == ["123", "stop"]
    fp0, fp1 = cs.fingerprint(entries[0]), cs.fingerprint(entries[1])

    run(_store().update(project, lambda d: cs.add_filter_items(d, -1, 0, fp0, "keywords", ["new word", "456"])))
    run(_store().update(project, lambda d: cs.add_filter_items(d, -1, 1, fp1, "whitelist", ["t.me/c/"])))
    text = project.config_path.read_text(encoding="utf-8")
    assert "? stop   # keep me" in text
    loaded = yaml.safe_load(text)
    assert loaded["filters"][0]["SkipWithKeywordsFilter"]["keywords"] == {"stop", "123", "new word", "456"}
    assert loaded["filters"][1]["UrlMessageFilter"]["whitelist"] == {"t.me/c/"}

    entry = cs.filters_of(cs.load(project).data, -1)[0]
    items = cs.filter_items(entry, "keywords")
    n = items.index("123")
    removed = []
    run(_store().update(project, lambda d: removed.append(cs.remove_filter_item(d, -1, 0, cs.fingerprint(entry), "keywords", n))))
    assert removed == ["123"]
    assert "123" not in yaml.safe_load(project.config_path.read_text(encoding="utf-8"))["filters"][0]["SkipWithKeywordsFilter"]["keywords"]


def test_direction_filter_list_items(tmp_path):
    project = _project(tmp_path, WITH_FILTERS)
    entry = cs.filters_of(cs.load(project).data, 0)[0]
    fp = cs.fingerprint(entry)
    run(_store().update(project, lambda d: cs.add_filter_items(d, 0, 0, fp, "keywords", ["c", "a"])))
    data = yaml.safe_load(project.config_path.read_text(encoding="utf-8"))
    assert data["directions"][0]["filters"][0]["AllowWithKeywordsFilter"]["keywords"] == ["a", "b", "c"]


def test_filter_edits_refuse_stale_or_uneditable(tmp_path):
    project = _project(tmp_path, WITH_FILTERS)
    entries = cs.filters_of(cs.load(project).data, -1)
    with pytest.raises(cs.ConfigError) as e:
        run(_store().update(project, lambda d: cs.add_filter_items(d, -1, 0, "deadbeef", "keywords", ["x"])))
    assert e.value.code == "stale"
    with pytest.raises(cs.ConfigError) as e:
        run(_store().update(project, lambda d: cs.add_filter_items(d, -1, 2, cs.fingerprint(entries[2]), "format", ["x"])))
    assert e.value.code == "bad_filter"


# ── whole filters ───────────────────────────────────────────────────────────


def _loaded(project):
    return yaml.safe_load(project.config_path.read_text(encoding="utf-8"))


def test_add_filter_puts_skip_filters_first_and_the_rest_last(tmp_path):
    project = _project(tmp_path, WITH_FILTERS)
    run(_store().update(project, lambda d: cs.add_filter(d, -1, "", "SkipWithUrlFilter", ["t.me/spam"])))
    run(_store().update(project, lambda d: cs.add_filter(d, -1, "", "RestrictSavingContentBypassFilter")))
    names = [cs.filter_name(f) for f in _loaded(project)["filters"]]
    assert names == ["SkipWithKeywordsFilter", "SkipWithUrlFilter", "UrlMessageFilter", "ForwardFormatFilter",
                     "RestrictSavingContentBypassFilter"]
    assert _loaded(project)["filters"][1]["SkipWithUrlFilter"]["blacklist"] == {"t.me/spam"}
    assert "? stop   # keep me" in project.config_path.read_text(encoding="utf-8")


def test_add_filter_refuses_missing_required_and_unknown(tmp_path):
    project = _project(tmp_path, WITH_FILTERS)
    for name, items in (("SkipWithKeywordsFilter", None), ("MappedNameForwardFormat", None), ("os", None)):
        with pytest.raises(cs.ConfigError):
            run(_store().update(project, lambda d, n=name, i=items: cs.add_filter(d, -1, "", n, i)))


def test_first_own_filter_of_a_direction_copies_the_projects(tmp_path):
    project = _project(tmp_path, WITH_FILTERS)
    copied = []
    run(_store().update(project, lambda d: copied.append(cs.add_filter(d, 1, _fp(project, 1), "SkipUrlFilter"))))
    own = [cs.filter_name(f) for f in _loaded(project)["directions"][1]["filters"]]
    assert copied == [True]
    assert own == ["SkipWithKeywordsFilter", "SkipUrlFilter", "UrlMessageFilter", "ForwardFormatFilter"]
    with pytest.raises(cs.ConfigError) as e:  # the direction changed: its fingerprint is stale
        run(_store().update(project, lambda d: cs.add_filter(d, 1, "deadbeef", "SkipAllFilter")))
    assert e.value.code == "stale"


def test_delete_and_move_filters(tmp_path):
    project = _project(tmp_path, WITH_FILTERS)
    entries = cs.filters_of(cs.load(project).data, -1)
    run(_store().update(project, lambda d: cs.move_filter(d, -1, 0, cs.fingerprint(entries[0]), 1)))
    assert [cs.filter_name(f) for f in _loaded(project)["filters"]][:2] == ["UrlMessageFilter", "SkipWithKeywordsFilter"]
    with pytest.raises(cs.ConfigError):  # past the end
        run(_store().update(project, lambda d: cs.move_filter(d, -1, 2, cs.fingerprint(entries[2]), 1)))
    own = cs.filters_of(cs.load(project).data, 0)[0]
    run(_store().update(project, lambda d: cs.delete_filter(d, 0, 0, cs.fingerprint(own))))
    assert "filters" not in _loaded(project)["directions"][0]  # the last own one: back to the project's


def test_scalar_args_turn_a_bare_entry_into_a_mapping(tmp_path):
    project = _project(tmp_path, "filters:\n  - SkipUrlFilter\ndirections: []\n")
    entry = cs.filters_of(cs.load(project).data, -1)[0]
    assert [(a.key, a.kind, a.default) for a in cs.filter_args(entry)] == [("skip_mention", "bool", True)]
    run(_store().update(project, lambda d: cs.set_filter_arg(d, -1, 0, cs.fingerprint(entry), "skip_mention", False)))
    assert _loaded(project)["filters"] == [{"SkipUrlFilter": {"skip_mention": False}}]
    entry = cs.filters_of(cs.load(project).data, -1)[0]
    run(_store().update(project, lambda d: cs.set_filter_arg(d, -1, 0, cs.fingerprint(entry), "skip_mention", None)))
    assert _loaded(project)["filters"] == [{"SkipUrlFilter": {}}]
    with pytest.raises(cs.ConfigError) as e:  # a list-like arg isn't set as a scalar
        run(_store().update(project, lambda d: cs.set_filter_arg(
            d, -1, 0, cs.fingerprint(cs.filters_of(d, -1)[0]), "keywords", "x")))
    assert e.value.code == "bad_filter"


def test_text_format_and_map_items(tmp_path):
    project = _project(tmp_path, WITH_FILTERS)
    fmt = cs.filters_of(cs.load(project).data, -1)[2]
    run(_store().update(project, lambda d: cs.set_filter_arg(d, -1, 2, cs.fingerprint(fmt), "format", "{message_text}\n— src")))
    assert _loaded(project)["filters"][2]["ForwardFormatFilter"]["format"] == "{message_text}\n— src"
    run(_store().update(project, lambda d: cs.add_filter(d, -1, "", "KeywordReplaceFilter", [("a", "b")])))
    n = [cs.filter_name(f) for f in cs.filters_of(cs.load(project).data, -1)].index("KeywordReplaceFilter")
    entry = cs.filters_of(cs.load(project).data, -1)[n]
    run(_store().update(project, lambda d: cs.add_filter_items(d, -1, n, cs.fingerprint(entry), "keywords",
                                                                cs.parse_items("map", "c => d\na => z"))))
    assert _loaded(project)["filters"][n]["KeywordReplaceFilter"]["keywords"] == {"a": "z", "c": "d"}
    entry = cs.filters_of(cs.load(project).data, -1)[n]
    assert cs.filter_items(entry, "keywords") == ["a => z", "c => d"]
    run(_store().update(project, lambda d: cs.remove_filter_item(d, -1, n, cs.fingerprint(entry), "keywords", 0)))
    assert _loaded(project)["filters"][n]["KeywordReplaceFilter"]["keywords"] == {"c": "d"}


def test_kinds_follow_the_value_in_the_file():
    entry = {"WatermarkRemovalFilter": {"channels": [-1001111111111], "stamp_opacity": 0.5, "x": None}}
    kinds = {a.key: a.kind for a in cs.filter_args(entry)}
    assert kinds["channels"] == "ids" and kinds["stamp_opacity"] == "number" and kinds["x"] == ""
    assert kinds["remove_watermark"] == "bool"  # not in the file: from the catalog
    assert cs.editable_args({"AllowWithKeywordsFilter": {"keywords": ["a"]}}) == ("keywords",)


def test_watermark_catalog_covers_watermark_config():
    """Every WatermarkConfig field is editable from the panel, with its default."""
    from dataclasses import fields

    from telemirror.watermark.processor import WatermarkConfig

    catalog = {key: default for key, _, default in cs.FILTER_ARGS["WatermarkRemovalFilter"]}
    defaults = {f.name: f.default for f in fields(WatermarkConfig)}
    assert set(catalog) - {"channels"} == set(defaults)
    assert {k: v for k, v in catalog.items() if v is not None and k != "channels"} == {
        k: v for k, v in defaults.items() if k not in ("template_path", "stamp_watermark_path")}


def test_mention_names_replace_the_bool_and_back(tmp_path):
    project = _project(tmp_path, WITH_FILTERS)
    entry = cs.filters_of(cs.load(project).data, -1)[1]  # UrlMessageFilter
    assert cs.bool_or_set(entry, "filter_mention") and not cs.bool_or_set(entry, "blacklist")
    run(_store().update(project, lambda d: cs.set_filter_arg(d, -1, 1, cs.fingerprint(entry), "filter_mention", True)))
    entry = cs.filters_of(cs.load(project).data, -1)[1]
    run(_store().update(project, lambda d: cs.add_filter_items(
        d, -1, 1, cs.fingerprint(entry), "filter_mention", ["@a", "@b"])))
    assert _loaded(project)["filters"][1]["UrlMessageFilter"]["filter_mention"] == {"@a", "@b"}
    for _ in range(2):
        entry = cs.filters_of(cs.load(project).data, -1)[1]
        assert {a.key: a.kind for a in cs.filter_args(entry)}["filter_mention"] == "set"
        fp = cs.fingerprint(entry)
        run(_store().update(project, lambda d, fp=fp: cs.remove_filter_item(d, -1, 1, fp, "filter_mention", 0)))
    assert "filter_mention" not in _loaded(project)["filters"][1]["UrlMessageFilter"]  # the default (false) again
    with pytest.raises(cs.ConfigError) as e:  # an ordinary bool doesn't take names
        run(_store().update(project, lambda d: cs.add_filter_items(
            d, -1, 1, cs.fingerprint(cs.filters_of(d, -1)[1]), "filter_by_id_mention", ["@a"])))
    assert e.value.code == "bad_filter"


def test_item_parsers():
    assert cs.parse_items("ids", "-1001111111111, -1001111111111\n-1002222222222") == [-1001111111111, -1002222222222]
    assert cs.parse_items("map", "-1001111111111 => Канал", int_keys=True) == [(-1001111111111, "Канал")]
    assert cs.parse_number("0,5") == 0.5 and cs.parse_number("3") == 3
    for kind, raw in (("map", "no arrow"), ("map", " => x"), ("ids", "abc")):
        with pytest.raises(cs.ConfigError):
            cs.parse_items(kind, raw)
    with pytest.raises(cs.ConfigError):
        cs.parse_number("x")


# ── a direction's link, the replay's pause ──────────────────────────────────


def test_direction_link_and_replay_delay(tmp_path):
    project = _project(tmp_path, WITH_FILTERS)
    run(_store().update(project, lambda d: cs.set_direction_value(d, 0, _fp(project, 0), "fallback_link_url", "https://t.me/x")))
    assert _loaded(project)["directions"][0]["fallback_link_url"] == "https://t.me/x"
    assert cs.replay_delays(cs.load(project).data) == [2.0]
    run(_store().update(project, lambda d: cs.set_replay_delay(d, 3.5)))
    assert _loaded(project)["directions"][1]["past_mode"] == {"last_n": 5, "send_delay": 3.5}
    run(_store().update(project, lambda d: cs.set_replay_delay(d, None)))
    assert _loaded(project)["directions"][1]["past_mode"] == {"last_n": 5}
    (tmp_path / "e").mkdir()
    empty = _project(tmp_path / "e", "directions: []\n")
    with pytest.raises(cs.ConfigError) as e:
        run(_store().update(empty, lambda d: cs.set_replay_delay(d, 1.0)))
    assert e.value.code == "no_history"


def test_one_directions_replay_delay(tmp_path):
    project = _project(tmp_path, WITH_FILTERS)
    run(_store().update(project, lambda d: cs.set_direction_replay_delay(d, 1, _fp(project, 1), 4.5)))
    assert _loaded(project)["directions"][1]["past_mode"] == {"last_n": 5, "send_delay": 4.5}
    run(_store().update(project, lambda d: cs.set_direction_replay_delay(d, 1, _fp(project, 1), None)))
    assert _loaded(project)["directions"][1]["past_mode"] == {"last_n": 5}
    with pytest.raises(cs.ConfigError) as e:  # no history: nothing to pause
        run(_store().update(project, lambda d: cs.set_direction_replay_delay(d, 0, _fp(project, 0), 1.0)))
    assert e.value.code == "no_history"
    with pytest.raises(cs.ConfigError) as e:
        run(_store().update(project, lambda d: cs.set_direction_replay_delay(d, 1, "stale", 1.0)))
    assert e.value.code == "stale"


# ── parsing ─────────────────────────────────────────────────────────────────


def test_value_parsers():
    assert cs.parse_channel_id("-1001234567890") == -1001234567890
    assert cs.parse_delay("0,5") == 0.5
    assert cs.parse_last_n("100") == 100
    assert cs.parse_since("2024-01-31") == "2024-01-31"
    assert cs.parse_url("https://t.me/x") == "https://t.me/x"
    assert cs.parse_filter_items("a, b\n\n c \na, b") == ["a, b", "c"]
    for fn, raw in [
        (cs.parse_channel_id, "-1001234567890#3"), (cs.parse_delay, "61"), (cs.parse_delay, "x"),
        (cs.parse_last_n, "0"), (cs.parse_last_n, "-5"), (cs.parse_since, "31.01.2024"),
        (cs.parse_url, "t.me/x"), (cs.parse_url, "https://a b"), (cs.parse_filter_items, " \n "),
        (cs.parse_filter_items, "x" * 201),
    ]:
        with pytest.raises(cs.ConfigError):
            fn(raw)


# ── whole-file replace / rollback ───────────────────────────────────────────


def test_replace_text_and_rollback_swap(tmp_path):
    project = _project(tmp_path, PYYAML_STYLE)
    new = "directions:\n  - from: [-1007777777777]\n    to: [-1008888888888]\n"
    snap = cs.load(project)
    run(_store().replace_text(project, new, snap.sha))
    assert project.config_path.read_text(encoding="utf-8") == new
    assert cs.backup_info(project).directions == 2
    run(_store().restore_backup(project))  # back to the original…
    assert project.config_path.read_text(encoding="utf-8") == PYYAML_STYLE
    run(_store().restore_backup(project))  # …and the rollback itself is undoable
    assert project.config_path.read_text(encoding="utf-8") == new


def test_replace_text_refusals(tmp_path):
    project = _project(tmp_path, PYYAML_STYLE)
    for text, code in [
        ("key: [unclosed", "bad_yaml"),
        ("just: a mapping\n", "bad_yaml"),
        ("directions: []\n# " + "x" * (cs.MAX_UPLOAD_BYTES + 1), "too_big"),
    ]:
        with pytest.raises(cs.ConfigError) as e:
            run(_store().replace_text(project, text))
        assert e.value.code == code
    with pytest.raises(cs.ConfigError) as e:
        run(_store().replace_text(project, "directions: []\n", expected_sha="0" * 64))
    assert e.value.code == "changed_on_disk"
    assert project.config_path.read_text(encoding="utf-8") == PYYAML_STYLE


def test_restore_without_backup(tmp_path):
    project = _project(tmp_path, PYYAML_STYLE)
    assert cs.backup_info(project) is None
    with pytest.raises(cs.ConfigError) as e:
        run(_store().restore_backup(project))
    assert e.value.code == "no_backup"


def test_text_diff():
    assert cs.text_diff("a\nb\n", "a\nb\n") == ("", False)
    diff, truncated = cs.text_diff("a\nb\nc\n", "a\nB\nc\n")
    assert "-b" in diff and "+B" in diff and not truncated
    diff, truncated = cs.text_diff("", "x\n" * 2000, limit=100)
    assert truncated and len(diff) == 100
