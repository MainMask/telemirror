"""Every mirror config shown in README.md must load through config.py, so the
docs can't drift from the load-time validation again."""

import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_BLOCKS = [
    textwrap.dedent(block)
    for block in re.findall(
        r"```yaml\n(.*?)```", (ROOT / "README.md").read_text(encoding="utf8"), re.S
    )
    if "directions:" in block
]


def test_readme_has_a_config_example():
    assert _BLOCKS


@pytest.mark.parametrize(
    "yaml_cfg", _BLOCKS, ids=[f"block{i}" for i in range(len(_BLOCKS))]
)
def test_readme_config_example_loads(yaml_cfg):
    # Subprocess: config.py builds CHAT_MAPPING at import time (see
    # test_config.py::test_direction_level_filters_are_built_once_per_direction).
    out = subprocess.run(
        [sys.executable, "-c", "from config import CHAT_MAPPING; print(len(CHAT_MAPPING))"],
        cwd=ROOT,
        env={**os.environ, "YAML_CONFIG_ENV": yaml_cfg},
        capture_output=True, text=True,
    )
    assert out.returncode == 0, out.stderr[-500:]
