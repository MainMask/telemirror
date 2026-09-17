import asyncio
import time

from telemirror.messagefilters._media import ReuploadCache, source_media_id
from telethon.tl import types
from tests.conftest import run


def test_hit_and_miss():
    c = ReuploadCache()
    assert c.get(1) is None
    c.put(1, "handle-1")
    assert c.get(1) == "handle-1"


def test_ttl_expiry(monkeypatch):
    c = ReuploadCache(ttl=10)
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    c.put(1, "h")
    now[0] = 1009
    assert c.get(1) == "h"
    now[0] = 1011
    assert c.get(1) is None


def test_lru_eviction():
    c = ReuploadCache(size=2)
    c.put(1, "a")
    c.put(2, "b")
    c.get(1)          # 1 becomes most-recent
    c.put(3, "c")     # evicts least-recent = 2
    assert c.get(1) == "a"
    assert c.get(2) is None
    assert c.get(3) == "c"


def test_get_or_create_single_flights_concurrent_callers():
    """Two concurrent callers for the same key (e.g. two in-flight
    event-handler tasks sharing a filter instance) must share one in-flight
    factory call instead of each redundantly re-running it — the bug this
    method exists to fix."""
    c = ReuploadCache()
    calls = 0

    async def factory():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)  # yield, so a naive implementation could race
        return "handle"

    async def scenario():
        return await asyncio.gather(
            c.get_or_create(1, factory),
            c.get_or_create(1, factory),
        )

    results = run(scenario())
    assert results == ["handle", "handle"]
    assert calls == 1
    assert c.get(1) == "handle"


def test_get_or_create_returns_cached_value_without_calling_factory():
    c = ReuploadCache()
    c.put(1, "cached")

    async def factory():
        raise AssertionError("factory must not run on a cache hit")

    assert run(c.get_or_create(1, factory)) == "cached"


def test_get_or_create_propagates_factory_exception_to_all_awaiters():
    c = ReuploadCache()

    async def factory():
        raise ValueError("boom")

    async def scenario():
        return await asyncio.gather(
            c.get_or_create(1, factory),
            c.get_or_create(1, factory),
            return_exceptions=True,
        )

    results = run(scenario())
    assert all(isinstance(r, ValueError) for r in results)
    assert c.get(1) is None  # a failure is never cached


def test_get_or_create_survives_one_awaiter_being_cancelled():
    """Cancelling one awaiter of get_or_create(key) must not cancel the
    shared in-flight factory out from under a sibling awaiter of the same
    key. Without asyncio.shield, a cancelled awaiting Task cancels whatever
    it's suspended on — including the shared inflight Task — breaking every
    other concurrent caller too, not just the one being cancelled."""
    c = ReuploadCache()
    calls = 0

    async def factory():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return "handle"

    async def scenario():
        task_a = asyncio.ensure_future(c.get_or_create(1, factory))
        task_b = asyncio.ensure_future(c.get_or_create(1, factory))
        await asyncio.sleep(0)  # let both register as awaiters of the same inflight
        task_a.cancel()
        try:
            await task_a
        except asyncio.CancelledError:
            pass
        return await task_b

    result = run(scenario())
    assert result == "handle"
    assert calls == 1
    assert c.get(1) == "handle"


def test_get_or_create_respects_cacheable_predicate():
    c = ReuploadCache()
    calls = 0

    async def factory():
        nonlocal calls
        calls += 1
        return "sentinel"

    result = run(c.get_or_create(1, factory, cacheable=lambda v: False))
    assert result == "sentinel"
    assert c.get(1) is None  # not cached

    run(c.get_or_create(1, factory, cacheable=lambda v: False))
    assert calls == 2  # factory re-ran since nothing was cached


def test_source_media_id():
    photo = types.MessageMediaPhoto(
        photo=types.Photo(
            id=42, access_hash=0, file_reference=b"", date=None,
            sizes=[], dc_id=1,
        )
    )
    assert source_media_id(photo) == 42

    doc = types.MessageMediaDocument(
        document=types.Document(
            id=7, access_hash=0, file_reference=b"", date=None,
            mime_type="x", size=1, dc_id=1, attributes=[],
        )
    )
    assert source_media_id(doc) == 7

    assert source_media_id(types.MessageMediaWebPage(webpage=types.WebPageEmpty(id=0))) is None
    assert source_media_id(None) is None
