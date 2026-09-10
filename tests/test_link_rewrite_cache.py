"""Pass 10 (perf): link resolution in the fan-out must be done once per event,
not once per target/config.

``EventProcessor._rewrite_links`` used to re-run ``get_messages`` (a DB round-trip)
and ``get_entity`` (a network round-trip) for every t.me link for every fan-out
target, even though the result depends only on ``(url, fallback_link_url)``.
"""

import logging
from types import SimpleNamespace

from telethon import utils
from telethon.tl import types

import telemirror.mirroring as mirroring
from config import DirectionConfig
from telemirror.messagefilters import EmptyMessageFilter
from telemirror.mirroring import EventProcessor
from telemirror.storage import InMemoryDatabase, MirrorMessage
from tests.conftest import make_message, run

SOURCE = -1001000000000
TARGET_A = -1002000000001
TARGET_B = -1002000000002
REF_RAW = 2000000009
REF = utils.get_peer_id(types.PeerChannel(REF_RAW))
REF_MIRROR = -1002000000077


def _cfg():
    return DirectionConfig(
        disable_delete=False, disable_edit=False, filters=EmptyMessageFilter()
    )


class _CountingDB(InMemoryDatabase):
    def __init__(self):
        super().__init__()
        self.get_messages_calls = 0

    async def get_messages(self, original_id, original_channel):
        # count only link-resolution lookups (against the referenced channel),
        # not the unrelated per-message dedup guard in new_message
        if original_channel == REF:
            self.get_messages_calls += 1
        return await super().get_messages(original_id, original_channel)


def test_link_resolution_is_cached_across_fanout(monkeypatch):
    db = run(_CountingDB())
    run(db.insert(MirrorMessage(5, REF, 500, REF_MIRROR)))

    async def fake_send_message(client, entity, message, **kw):
        return types.Message(id=1, peer_id=types.PeerChannel(1), message="x")

    monkeypatch.setattr(mirroring, "send_message", fake_send_message)

    proc = EventProcessor(
        chat_mapping={
            SOURCE: {TARGET_A: [_cfg()], TARGET_B: [_cfg()]},
            REF: {REF_MIRROR: [_cfg()]},
        },
        database=db,
        client=object(),
        logger=logging.getLogger("test.linkcache"),
    )

    msg = make_message(
        "link",
        entities=[
            types.MessageEntityTextUrl(
                offset=0, length=4, url=f"https://t.me/c/{REF_RAW}/5"
            )
        ],
        channel_id=1000,
    )
    msg._chat = SimpleNamespace(noforwards=False)

    run(proc.new_message(SOURCE, msg, "link"))

    # 2 fan-out targets, but the referenced link is resolved once.
    assert db.get_messages_calls == 1


def test_username_resolution_is_cached_on_the_processor():
    calls = []

    class FakeClient:
        async def get_entity(self, username):
            calls.append(username)
            return types.PeerChannel(REF_RAW)

    proc = EventProcessor(
        chat_mapping={}, database=object(), client=FakeClient(),
        logger=logging.getLogger("test.linkcache"),
    )
    msg = make_message("x", channel_id=1000)
    msg._chat = SimpleNamespace(username=None)

    first = run(proc._resolve_username_to_channel_id("somechan", SOURCE, msg))
    second = run(proc._resolve_username_to_channel_id("SomeChan", SOURCE, msg))

    assert first == second
    assert calls == ["somechan"]  # second call served from cache
