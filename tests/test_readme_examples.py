"""Every mirror config shown in README.md must load through telemirror.config, so the
docs can't drift from the load-time validation again."""

import re
import textwrap
from pathlib import Path

import pytest

from tests.conftest import import_config

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
def test_readme_config_example_loads(yaml_cfg, tmp_path):
    out = import_config(tmp_path, "from telemirror.config import CHAT_MAPPING; print(len(CHAT_MAPPING))", yaml_cfg)
    assert out.returncode == 0, out.stderr[-500:]
