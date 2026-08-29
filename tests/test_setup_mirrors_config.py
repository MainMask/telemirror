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
