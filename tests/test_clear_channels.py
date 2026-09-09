"""A7: clear_channels must only run whole-channel DeleteHistory on targets that
have no topic scoping in the config.

Pass 10: ``purge`` must sweep a channel's history once (not once per topic) and
route each message to the right topic.
"""

import types as _t

import pytest

from config import DirectionConfig
from skylon_set import clear_channels
from telemirror.messagefilters import EmptyMessageFilter
from tests.conftest import run


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


def _msg(mid, topic):
    reply_to = None
    if topic != 1:
        reply_to = _t.SimpleNamespace(
            forum_topic=True, reply_to_top_id=topic, reply_to_msg_id=topic
        )
    return _t.SimpleNamespace(id=mid, action=None, reply_to=reply_to)


class _FakeClient:
    def __init__(self, messages):
        self._messages = messages
        self.iter_calls = 0
        self.deleted: list = []

    def is_connected(self):
        return True

    async def connect(self):
        pass

    def iter_messages(self, channel_id):
        self.iter_calls += 1

        async def _gen():
            for m in self._messages:
                yield m

        return _gen()

    async def delete_messages(self, channel_id, ids):
        self.deleted.extend(ids)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    import skylon_set._common as common

    async def _noop(*_a, **_kw):
        pass

    monkeypatch.setattr(common.asyncio, "sleep", _noop)


def test_purge_sweeps_history_once_and_routes_by_topic():
    msgs = [_msg(1, 1), _msg(2, 7), _msg(3, 9), _msg(4, 7), _msg(5, 1)]
    client = _FakeClient(msgs)

    import logging

    deleted_count = run(
        clear_channels.purge(client, -100, {7, 9}, False, logging.getLogger("t"))
    )

    assert client.iter_calls == 1  # one pass for both topics, not one per topic
    assert sorted(client.deleted) == [2, 3, 4]  # topics 7 and 9 only
    assert deleted_count == 3
