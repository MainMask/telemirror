"""fetch_pinned union/de-dup + sync_pair orchestration against a fake client and
a real InMemoryDatabase."""

import logging

from telethon.tl import types

from skylon_set import sync_pins as sp
from skylon_set.sync_pins import SyncPair
from telemirror.storage import InMemoryDatabase, MirrorMessage
from tests.conftest import run

_LOG = logging.getLogger("test.sync_pins.fetch")
DONOR, RECIP = -1001, -9001


def _msg(mid, chat_id=DONOR):
    return types.Message(id=mid, peer_id=types.PeerChannel(abs(chat_id)), message=f"m{mid}")


class FakeClient:
    """`get_messages(filter=...)` -> whole-peer pins; `__call__(SearchRequest)` ->
    per-topic pins; `__call__(UpdatePinnedMessageRequest)` -> records the call."""

    def __init__(self, whole=None, per_topic=None):
        self._whole = whole or {}            # peer -> [Message]
        self._per_topic = per_topic or {}    # (peer, top_msg_id) -> [Message]
        self.pin_calls = []                  # (peer, id, unpin, silent)

    def is_connected(self):
        return True

    async def connect(self):
        pass

    async def disconnect(self):
        pass

    async def get_me(self):
        return types.User(id=1, bot=False)

    async def get_entity(self, cid):
        return cid

    async def get_messages(self, peer, filter=None, limit=None):
        return list(self._whole.get(peer, []))

    async def __call__(self, request):
        name = type(request).__name__
        if name == "SearchRequest":
            msgs = self._per_topic.get((request.peer, request.top_msg_id), [])
            return types.messages.ChannelMessages(
                pts=0, count=len(msgs), messages=list(msgs), topics=[], chats=[], users=[]
            )
        if name == "UpdatePinnedMessageRequest":
            self.pin_calls.append(
                (request.peer, request.id, request.unpin, request.silent)
            )
            return None
        raise AssertionError(f"unexpected request {name}")


def _no_sleep(monkeypatch):
    async def _noop(*_a, **_kw):
        pass

    monkeypatch.setattr("asyncio.sleep", _noop)


def _seed_db(pairs):
    db = run(InMemoryDatabase())
    run(db.insert_batch([MirrorMessage(o, DONOR, m, RECIP) for o, m in pairs]))
    return db


# --- fetch_pinned ---------------------------------------------------------

def test_fetch_pinned_unions_whole_and_per_topic(monkeypatch):
    _no_sleep(monkeypatch)
    client = FakeClient(
        whole={DONOR: [_msg(1), _msg(5)]},
        per_topic={(DONOR, 13): [_msg(5), _msg(9)]},
    )
    got = run(sp.fetch_pinned(client, DONOR, [13], 100, thorough=True, logger=_LOG))
    assert sorted(m.id for m in got) == [1, 5, 9]


def test_fetch_pinned_whole_only_without_thorough(monkeypatch):
    _no_sleep(monkeypatch)
    client = FakeClient(
        whole={DONOR: [_msg(1)]},
        per_topic={(DONOR, 13): [_msg(9)]},
    )
    got = run(sp.fetch_pinned(client, DONOR, [13], 100, thorough=False, logger=_LOG))
    assert [m.id for m in got] == [1]


# --- sync_pair ----------------------------------------------------------

def _pair():
    return SyncPair(DONOR, RECIP, topic_map={})


def _sync(client, db, **kw):
    kw.setdefault("reconcile", True)
    kw.setdefault("allow_clear", False)
    kw.setdefault("max_pins", 100)
    kw.setdefault("thorough", False)
    kw.setdefault("dry_run", False)
    return run(sp.sync_pair(client, db, _pair(), logger=_LOG, **kw))


def test_sync_pair_pins_missing(monkeypatch):
    _no_sleep(monkeypatch)
    db = _seed_db([(5, 905), (9, 909)])
    client = FakeClient(whole={DONOR: [_msg(9), _msg(5)], RECIP: [_msg(905, RECIP)]})
    s = _sync(client, db)
    assert client.pin_calls == [(RECIP, 909, None, True)]
    assert s.pinned == 1 and s.unpinned == 0


def test_sync_pair_reconcile_unpins_stale(monkeypatch):
    _no_sleep(monkeypatch)
    db = _seed_db([(5, 905), (3, 999)])
    # donor pins only msg 5; recipient currently has 905 + stale managed 999
    client = FakeClient(
        whole={DONOR: [_msg(5)], RECIP: [_msg(905, RECIP), _msg(999, RECIP)]}
    )
    _sync(client, db)
    assert (RECIP, 999, True, True) in client.pin_calls


def test_sync_pair_skips_unmapped_pin(monkeypatch):
    _no_sleep(monkeypatch)
    db = _seed_db([(5, 905)])
    client = FakeClient(whole={DONOR: [_msg(42)], RECIP: []})
    s = _sync(client, db)
    assert client.pin_calls == [] and s.skipped_no_binding == 1


def test_sync_pair_dry_run_makes_no_calls(monkeypatch):
    _no_sleep(monkeypatch)
    db = _seed_db([(9, 909)])
    client = FakeClient(whole={DONOR: [_msg(9)], RECIP: []})
    s = _sync(client, db, dry_run=True)
    assert client.pin_calls == [] and s.pinned == 1


def test_sync_pair_pins_oldest_first(monkeypatch):
    _no_sleep(monkeypatch)
    db = _seed_db([(5, 905), (7, 907), (9, 909)])
    client = FakeClient(whole={DONOR: [_msg(9), _msg(7), _msg(5)], RECIP: []})
    _sync(client, db)
    assert [c[1] for c in client.pin_calls] == [905, 907, 909]


def test_sync_pair_no_bindings_warns_and_skips(monkeypatch):
    _no_sleep(monkeypatch)
    db = run(InMemoryDatabase())
    client = FakeClient(whole={DONOR: [_msg(9)], RECIP: []})
    s = _sync(client, db)
    assert client.pin_calls == [] and s.desired == 0
