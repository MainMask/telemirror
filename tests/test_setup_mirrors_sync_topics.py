"""`setup_mirrors._sync_forum_topics` must be idempotent: create only the donor
topics the recipient is missing (by title), never the General topic, and toggle
the forum on only when asked. It is called on `step_create_pairs`' OK branch to
backfill topics after a FloodWait abort, so re-runs must not duplicate.
"""

import pytest

import skylon_set._common as common
from skylon_set import setup_mirrors as sm
from tests.conftest import run


class _Topic:
    def __init__(self, tid, title):
        self.id = tid
        self.title = title
        self.icon_color = 7
        self.top_message = tid
        self.date = tid


class _Deleted:
    def __init__(self, tid):
        self.id = tid


class _Result:
    def __init__(self, topics):
        self.topics = topics


class _FakeClient:
    def __init__(self, topics_by_peer):
        self._topics = {p: list(t) for p, t in topics_by_peer.items()}
        self.created = []          # (peer, title)
        self.toggled = []          # peers ToggleForumRequest was sent for

    def is_connected(self):
        return True

    async def connect(self):
        pass

    async def __call__(self, request):
        name = type(request).__name__
        if name == "GetForumTopicsRequest":
            return _Result(self._topics.get(request.peer, []))
        if name == "ToggleForumRequest":
            self.toggled.append(request.channel)
            return None
        if name == "CreateForumTopicRequest":
            self.created.append((request.peer, request.title))
            self._topics.setdefault(request.peer, []).append(
                _Topic(1000 + len(self.created), request.title)
            )
            return None
        raise AssertionError(f"unexpected request {name}")


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    async def _noop(*_a, **_kw):
        pass

    monkeypatch.setattr(common.asyncio, "sleep", _noop)


def test_creates_only_missing_skips_general_and_deleted():
    client = _FakeClient({
        "donor": [_Topic(1, "General"), _Topic(5, "Alpha"),
                  _Deleted(6), _Topic(9, "Beta")],
        "recip": [_Topic(1, "General"), _Topic(77, "Alpha")],
    })

    run(sm._sync_forum_topics(client, "donor", "recip", enable_forum=False))

    assert client.created == [("recip", "Beta")]   # Alpha exists, General & deleted skipped
    assert client.toggled == []


def test_enable_forum_toggles_first():
    client = _FakeClient({"donor": [_Topic(1, "General")], "recip": []})
    run(sm._sync_forum_topics(client, "donor", "recip", enable_forum=True))
    assert client.toggled == ["recip"]


def test_idempotent_second_run_creates_nothing():
    client = _FakeClient({
        "donor": [_Topic(1, "General"), _Topic(5, "Alpha")],
        "recip": [_Topic(1, "General")],
    })
    run(sm._sync_forum_topics(client, "donor", "recip", enable_forum=False))
    run(sm._sync_forum_topics(client, "donor", "recip", enable_forum=False))
    assert client.created == [("recip", "Alpha")]
