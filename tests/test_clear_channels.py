"""A7: clear_channels must only run whole-channel DeleteHistory on targets that
have no topic scoping in the config."""

import importlib.util
import sys
from pathlib import Path

from config import DirectionConfig
from telemirror.messagefilters import EmptyMessageFilter

_MOD = Path(__file__).resolve().parent.parent / "skylon_set" / "clear_channels.py"
_spec = importlib.util.spec_from_file_location("clear_channels", _MOD)
clear_channels = importlib.util.module_from_spec(_spec)
sys.modules["clear_channels"] = clear_channels
_spec.loader.exec_module(clear_channels)


def _cfg(topic=None):
    return DirectionConfig(
        disable_delete=False,
        disable_edit=False,
        filters=EmptyMessageFilter(),
        to_topic_id=topic,
    )


def test_channels_for_full_clear_excludes_topic_scoped():
    src1, src2, src3 = -1001, -1002, -1003
    whole, topic_only, mixed = -9001, -9002, -9003
    mapping = {
        src1: {whole: [_cfg(topic=None)]},
        src2: {topic_only: [_cfg(topic=3), _cfg(topic=5)]},
        src3: {mixed: [_cfg(topic=3), _cfg(topic=None)]},
    }
    targets = clear_channels.collect_targets(mapping)
    full = set(clear_channels.channels_for_full_clear(targets))
    assert full == {whole, mixed}
