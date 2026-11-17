"""Panel config writes: comments survive, refusals leave the file untouched,
and every candidate is validated by config.py itself."""

from pathlib import Path

import pytest
import yaml

from telemirror.panel import configstore as cs
from telemirror.panel.settings import Project
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


def _project(tmp_path, text, loader="file"):
    path = tmp_path / "mirror.config.yml"
    path.write_text(text, encoding="utf-8")
    return Project("t", path, "live", loader, live=False)


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

    text = project.path.read_text(encoding="utf-8")
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
    assert project.path.with_suffix(".yml.bak").read_text(encoding="utf-8") == EXAMPLE.read_text(
        encoding="utf-8"
    )


def test_pyyaml_style_file_keeps_its_indentation(tmp_path):
    project = _project(tmp_path, PYYAML_STYLE)
    snap = cs.load(project)
    fp = cs.fingerprint(cs.directions(snap.data)[0])
    run(_store().update(project, lambda d: cs.toggle_direction_flag(d, 0, fp, "disable_edit")))
    text = project.path.read_text(encoding="utf-8")
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
    data = yaml.safe_load(project.path.read_text(encoding="utf-8"))
    assert len(data["directions"]) == 1
    assert data["disable_edit"] is False
    assert data["mode"] == "forward"


def test_stale_fingerprint_refused(tmp_path):
    project = _project(tmp_path, PYYAML_STYLE)
    with pytest.raises(cs.ConfigError) as e:
        run(_store().update(project, lambda d: cs.delete_direction(d, 0, "deadbeef")))
    assert e.value.code == "stale"
    assert project.path.read_text(encoding="utf-8") == PYYAML_STYLE
    assert not project.path.with_suffix(".yml.bak").exists()


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
    assert project.path.read_text(encoding="utf-8") == PYYAML_STYLE


def test_validator_failure_leaves_file_untouched(tmp_path):
    project = _project(tmp_path, PYYAML_STYLE)

    async def reject(_project, _text):
        return "ValueError: nope"

    with pytest.raises(cs.ConfigError) as e:
        run(_store(reject).update(project, lambda d: cs.toggle_global(d, "mode")))
    assert (e.value.code, e.value.detail) == ("invalid", "ValueError: nope")
    assert project.path.read_text(encoding="utf-8") == PYYAML_STYLE


def test_manual_edit_during_write_refused(tmp_path):
    project = _project(tmp_path, PYYAML_STYLE)

    async def edit_meanwhile(_project, _text):
        project.path.write_text(PYYAML_STYLE + "# hand edit\n", encoding="utf-8")
        return None

    with pytest.raises(cs.ConfigError) as e:
        run(_store(edit_meanwhile).update(project, lambda d: cs.toggle_global(d, "mode")))
    assert e.value.code == "changed_on_disk"
    assert project.path.read_text(encoding="utf-8").endswith("# hand edit\n")


def test_read_only_reasons(tmp_path, monkeypatch):
    live = Project("live", tmp_path / "mirror.config.yml", "live", "file", live=True)
    courses = Project("crs", tmp_path / "courses.yml", "crs", "env", live=False)
    monkeypatch.setattr(cs.settings, "YAML_CONFIG_ENV_SET", False)
    assert cs.read_only_reason(live) == "env_mode"
    assert cs.read_only_reason(courses) == "missing"
    live.path.write_text(PYYAML_STYLE, encoding="utf-8")
    assert cs.read_only_reason(live) is None
    monkeypatch.setattr(cs.settings, "YAML_CONFIG_ENV_SET", True)
    assert cs.read_only_reason(live) == "yaml_env"
    with pytest.raises(cs.ConfigError) as e:
        run(_store().update(live, lambda d: cs.toggle_global(d, "mode")))
    assert e.value.code == "read_only"


def test_fingerprint_is_stable_and_content_sensitive():
    a = {"from": [-1001], "to": [-1002], "filters": [{"SkipWithKeywordsFilter": {"keywords": {"b", "a"}}}]}
    b = {"from": [-1001], "to": [-1002], "filters": [{"SkipWithKeywordsFilter": {"keywords": {"a", "b"}}}]}
    assert cs.fingerprint(a) == cs.fingerprint(b)
    assert cs.fingerprint(a) != cs.fingerprint({**a, "mode": "forward"})
    assert len(cs.fingerprint(a)) == 8


# ── the real validator: config.py in a subprocess ───────────────────────────


@pytest.mark.parametrize("loader", ["file", "env"])
def test_validate_with_config_py(tmp_path, loader):
    project = _project(tmp_path, "", loader=loader)
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
