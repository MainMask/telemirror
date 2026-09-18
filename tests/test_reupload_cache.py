import asyncio
import time

from telemirror.messagefilters._media import (
    ReuploadCache,
    cached_media_result,
    source_media_id,
)
from telemirror.messagefilters.base import FilterAction
from telethon.tl import types
from tests.conftest import make_message, run


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


def test_get_or_create_no_redundant_factory_for_caller_arriving_at_cleanup():
    """A caller landing in the single tick where the in-flight entry's
    done-callback (`_cleanup`) has just deleted `self._inflight[key]`, but
    the original awaiter hasn't yet resumed past `await asyncio.shield(...)`
    to cache the result, must still see the cached value rather than
    restarting `factory()` — the exact race window `_cleanup` firing before
    the result is cached could open. Reproduced deterministically by hooking
    `_inflight`'s `__delitem__` (fired by `_cleanup`) to schedule the late
    caller for the very next loop iteration, matching where the real race
    window used to land."""
    c = ReuploadCache()
    calls = 0
    late_caller: list = []

    class _NotifyingInflight(dict):
        def __delitem__(self, key):
            super().__delitem__(key)
            late_caller.append(asyncio.ensure_future(c.get_or_create(1, factory)))

    c._inflight = _NotifyingInflight()

    async def factory():
        nonlocal calls
        calls += 1
        return "handle"

    async def scenario():
        first = await c.get_or_create(1, factory)
        late = await late_caller[0]
        return first, late

    first, late = run(scenario())
    assert calls == 1
    assert first == late == "handle"


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


def test_get_or_create_cacheable_decided_only_by_entry_creating_caller():
    """`cacheable` is evaluated once, by whichever concurrent caller's
    `_run()` created the in-flight entry — a caller that instead finds an
    existing in-flight task and just awaits it never gets its own
    `cacheable` argument consulted (see `get_or_create`'s docstring). Pins
    down that documented precondition: every caller sharing a key must agree
    on the caching policy for it, since only the creator's predicate runs."""
    c = ReuploadCache()

    async def factory():
        await asyncio.sleep(0)  # yield, so the second call arrives mid-flight
        return "handle"

    async def scenario():
        return await asyncio.gather(
            c.get_or_create(1, factory, cacheable=lambda v: False),  # creator
            c.get_or_create(1, factory, cacheable=lambda v: True),  # joins in-flight
        )

    results = run(scenario())
    assert results == ["handle", "handle"]
    assert c.get(1) is None  # the joiner's cacheable=True was never consulted


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


def _photo(id_):
    return types.MessageMediaPhoto(
        photo=types.Photo(
            id=id_, access_hash=0, file_reference=b"", date=None,
            sizes=[], dc_id=1,
        )
    )


def test_cached_media_result_none_when_nothing_cached():
    c = ReuploadCache()
    msg = make_message(media=_photo(1))
    assert cached_media_result(c, msg) is None
    assert msg.media == _photo(1)  # untouched


def test_cached_media_result_applies_cached_media_and_continues():
    c = ReuploadCache()
    run(c.get_or_create(1, lambda: asyncio.sleep(0, result="UPLOADED"), lambda v: True))

    msg = make_message(media=_photo(1))
    result = cached_media_result(c, msg)

    assert result is not None
    assert result.action is FilterAction.CONTINUE
    assert result.entity.media == "UPLOADED"
    assert msg.media == "UPLOADED"
