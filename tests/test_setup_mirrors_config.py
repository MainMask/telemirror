"""A8: build-config must preserve hand-maintained keys and back up the old file."""

import yaml

from skylon_set import setup_mirrors


def test_write_directions_preserves_other_keys_and_backs_up(tmp_path):
    cfg = tmp_path / "mirror.config.yml"
    cfg.write_text(
        yaml.safe_dump(
            {
                "filters": [{"UrlMessageFilter": {"blacklist": ["t.me"]}}],
                "broadcast_channel": -100123,
                "disable_edit": True,
                "directions": [{"from": [-1], "to": [-2]}],
            }
        ),
        encoding="utf-8",
    )

    new_dirs = [{"from": [-10], "to": [-20]}, {"from": ["-30#1"], "to": ["-40#1"]}]
    backup = setup_mirrors.write_directions(cfg, new_dirs)

    result = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    assert result["directions"] == new_dirs
    assert result["filters"] == [{"UrlMessageFilter": {"blacklist": ["t.me"]}}]
    assert result["broadcast_channel"] == -100123
    assert result["disable_edit"] is True

    assert backup is not None and backup.exists()
    assert yaml.safe_load(backup.read_text())["directions"] == [{"from": [-1], "to": [-2]}]


def test_write_directions_creates_file_when_absent(tmp_path):
    cfg = tmp_path / "sub" / "mirror.config.yml"
    backup = setup_mirrors.write_directions(cfg, [{"from": [-10], "to": [-20]}])
    assert backup is None
    assert yaml.safe_load(cfg.read_text())["directions"] == [{"from": [-10], "to": [-20]}]


def test_write_directions_merge_appends_new_dedupes_keeps_comments(tmp_path):
    cfg = tmp_path / "mirror.config.yml"
    cfg.write_text(
        "# hand-written header — must survive\n"
        "disable_delete: true\n"
        "directions:\n"
        "- from:\n  - -1\n  to:\n  - -2\n",
        encoding="utf-8",
    )

    new = [
        {"from": [-1], "to": [-2]},  # already present → skipped
        {"from": ["-3#5"], "to": ["-4#5"], "past_mode": {"full_history": True}},
    ]
    backup = setup_mirrors.write_directions(cfg, new, merge=True)

    text = cfg.read_text(encoding="utf-8")
    assert "# hand-written header — must survive" in text
    result = yaml.safe_load(text)
    assert result["disable_delete"] is True
    assert result["directions"] == [
        {"from": [-1], "to": [-2]},
        {"from": ["-3#5"], "to": ["-4#5"], "past_mode": {"full_history": True}},
    ]
    assert backup is not None and backup.exists()

    # nothing new on a second run → no-op, no backup churn
    backup2 = setup_mirrors.write_directions(cfg, [{"from": [-1], "to": [-2]}], merge=True)
    assert backup2 is None


def test_write_directions_merge_refuses_when_directions_not_last(tmp_path):
    cfg = tmp_path / "mirror.config.yml"
    cfg.write_text(
        "directions:\n- from:\n  - -1\n  to:\n  - -2\n"
        "broadcast_channel: -100999\n",
        encoding="utf-8",
    )
    try:
        setup_mirrors.write_directions(cfg, [{"from": [-9], "to": [-8]}], merge=True)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
