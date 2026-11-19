"""Pass 10: telemirror.tasks._common.fetch_all_topics must page past the 100-topic
API cap. The three copies it replaced in setup_mirrors passed limit=100 with no
pagination and silently truncated forums with >100 topics.

It also drops ForumTopicDeleted tombstones (id only, no .title) and pages from
the last *real* topic so a deleted tail element can't zero out the cursor.
"""

import pytest

import telemirror.tasks._common as common
from tests.conftest import run


class _Topic:
    def __init__(self, tid):
        self.id = tid
        self.title = f"topic {tid}"
        self.top_message = tid * 10
        self.date = tid


class _Deleted:
    """ForumTopicDeleted tombstone — carries only an id."""

    def __init__(self, tid):
        self.id = tid


class _Page:
    def __init__(self, topics):
        self.topics = topics


class _FakeClient:
    """Serves the given pages in order; records each request for assertions."""

    def __init__(self, pages):
        self._pages = list(pages)
        self.calls = 0
        self.requests = []

    @classmethod
    def with_sizes(cls, *sizes):
        """Pages of these sizes; topic ids run on across pages, as a forum's do."""
        starts = [sum(sizes[:k]) for k in range(len(sizes))]
        return cls(_Page([_Topic(start + i) for i in range(n)]) for start, n in zip(starts, sizes, strict=True))

    async def __call__(self, request):
        self.requests.append(request)
        page = self._pages[self.calls]
        self.calls += 1
        return page


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    async def _noop(*_a, **_kw):
        pass

    monkeypatch.setattr(common.asyncio, "sleep", _noop)


def test_paginates_until_short_page():
    client = _FakeClient.with_sizes(100, 100, 30)
    topics = run(common.fetch_all_topics(client, -100))
    assert len(topics) == 230
    assert client.calls == 3


def test_single_page_when_under_cap():
    client = _FakeClient.with_sizes(42)
    topics = run(common.fetch_all_topics(client, -100))
    assert len(topics) == 42
    assert client.calls == 1


def test_drops_deleted_topic_tombstones():
    client = _FakeClient([_Page([_Topic(1), _Deleted(2), _Topic(3)])])
    topics = run(common.fetch_all_topics(client, -100))
    assert [t.id for t in topics] == [1, 3]


def test_cursor_skips_deleted_tail_element():
    # full page whose last element is a tombstone → cursor must come from _Topic(98)
    page1 = _Page([_Topic(i) for i in range(99)] + [_Deleted(999)])
    client = _FakeClient([page1, _Page([_Topic(200)])])
    topics = run(common.fetch_all_topics(client, -100))

    assert [t.id for t in topics] == list(range(99)) + [200]
    assert client.requests[1].offset_topic == 98
    assert client.requests[1].offset_id == 980  # _Topic(98).top_message


def test_a_cursor_that_goes_round_ends_the_paging():
    """A full page of tombstones leaves only a zero cursor: if the API then
    serves the first page again, paging stops instead of looping forever."""
    first = _Page([_Topic(i) for i in range(1, 101)])
    tombstones = _Page([_Deleted(i) for i in range(101, 201)])
    client = _FakeClient([first, tombstones, first, first])
    topics = run(common.fetch_all_topics(client, "peer"))
    assert [t.id for t in topics] == list(range(1, 101)) and client.calls == 3
