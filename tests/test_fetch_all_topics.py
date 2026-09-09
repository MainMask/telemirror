"""Pass 10: skylon_set._common.fetch_all_topics must page past the 100-topic
API cap. The three copies it replaced in setup_mirrors passed limit=100 with no
pagination and silently truncated forums with >100 topics.
"""

import pytest

import skylon_set._common as common
from tests.conftest import run


class _Topic:
    def __init__(self, tid):
        self.id = tid
        self.title = f"topic {tid}"
        self.top_message = tid
        self.date = 0


class _Deleted:
    """ForumTopicDeleted tombstone — carries only an id."""

    def __init__(self, tid):
        self.id = tid


class _Page:
    def __init__(self, topics):
        self.topics = topics


class _FakeClient:
    def __init__(self, page_sizes):
        self._pages = [
            _Page([_Topic(i) for i in range(n)]) for n in page_sizes
        ]
        self.calls = 0

    async def __call__(self, request):
        page = self._pages[self.calls]
        self.calls += 1
        return page


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    async def _noop(*_a, **_kw):
        pass

    monkeypatch.setattr(common.asyncio, "sleep", _noop)


def test_paginates_until_short_page():
    client = _FakeClient([100, 100, 30])
    topics = run(common.fetch_all_topics(client, -100))
    assert len(topics) == 230
    assert client.calls == 3


def test_single_page_when_under_cap():
    client = _FakeClient([42])
    topics = run(common.fetch_all_topics(client, -100))
    assert len(topics) == 42
    assert client.calls == 1


def test_drops_deleted_topic_tombstones():
    client = _FakeClient.__new__(_FakeClient)
    client._pages = [_Page([_Topic(1), _Deleted(2), _Topic(3)])]
    client.calls = 0
    topics = run(common.fetch_all_topics(client, -100))
    assert [t.id for t in topics] == [1, 3]
