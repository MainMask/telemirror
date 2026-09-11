"""setup_citadel: forum-topic traversal must not be repeated, and the generated
``directions`` block must pair donor topics to recipient topics by title."""

import logging

import pytest
from telethon.tl import types

from skylon_set import setup_citadel as sc
from tests.conftest import run

_LOG = logging.getLogger("test.setup_citadel")


class _Topic:
    def __init__(self, tid, title, icon_color=7, icon_emoji_id=None):
        self.id = tid
        self.title = title
        self.icon_color = icon_color
        self.icon_emoji_id = icon_emoji_id
        self.top_message = tid
        self.date = 0


class _TopicsResult:
    def __init__(self, topics):
        self.topics = topics


class _FakeClient:
    """Records every ``GetForumTopicsRequest`` peer and every created topic."""

    def __init__(self, topics_by_peer):
        self._topics = {p: list(t) for p, t in topics_by_peer.items()}
        self.get_topics_calls = []          # list of peer ids
        self.created = []                   # (peer, title)
        self.parse_mode = None

    def is_connected(self):
        return True

    async def connect(self):
        pass

    async def disconnect(self):
        pass

    async def get_me(self):
        return types.User(id=1, first_name="T", bot=False)

    async def __call__(self, request):
        name = type(request).__name__
        if name == "GetForumTopicsRequest":
            self.get_topics_calls.append(request.peer)
            return _TopicsResult(self._topics.get(request.peer, []))
        if name == "CreateForumTopicRequest":
            self.created.append((request.peer, request.title))
            self._topics.setdefault(request.peer, []).append(
                _Topic(1000 + len(self.created), request.title)
            )
            return None
        raise AssertionError(f"unexpected request {name}")


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    import skylon_set._common as common

    async def _noop(*_a, **_kw):
        pass

    monkeypatch.setattr(sc.asyncio, "sleep", _noop)
    monkeypatch.setattr(common.asyncio, "sleep", _noop)


def test_build_forum_directions_pairs_by_title():
    donor = [_Topic(1, "General"), _Topic(5, "Alpha"), _Topic(9, "Beta")]
    recip = [_Topic(1, "General"), _Topic(77, "Alpha")]

    directions, missing = sc.build_forum_directions(-100, -200, donor, recip)

    assert directions == [
        {"from": ["-100#1"], "to": ["-200#1"], "past_mode": sc.PAST_MODE},
        {"from": ["-100#5"], "to": ["-200#77"], "past_mode": sc.PAST_MODE},
    ]
    assert missing == ["Beta"]


def test_run_traverses_each_forum_once_per_side_plus_recheck(monkeypatch):
    donor_id, recip_id = -1000, -2000
    monkeypatch.setattr(sc, "FORUM_PAIRS", [(donor_id, recip_id)])
    monkeypatch.setattr(sc, "CHANNEL_PAIRS", [])

    client = _FakeClient({
        donor_id: [_Topic(1, "General"), _Topic(5, "Alpha"), _Topic(9, "Beta")],
        recip_id: [_Topic(1, "General")],
    })
    monkeypatch.setattr("skylon_set._common.make_client", lambda **kw: client)
    monkeypatch.setattr("builtins.print", lambda *a, **kw: None)

    run(sc._run(_LOG))

    # donor is read once; recipient is read twice (before + after topic creation)
    assert client.get_topics_calls.count(donor_id) == 1
    assert client.get_topics_calls.count(recip_id) == 2
    # the two donor topics missing at the recipient were created
    assert sorted(t for _, t in client.created) == ["Alpha", "Beta"]
