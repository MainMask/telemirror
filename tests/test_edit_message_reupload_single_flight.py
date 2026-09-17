"""Two mirrors sharing a re-uploading filter instance (the common case —
directions sharing the top-level `default_filters`, per `ReuploadCache`'s own
docstring) must share one download+re-upload instead of each redundantly
repeating it.

`edit_message` itself fans out to its mirrors with a plain sequential `for`
loop, not `asyncio.gather` — the sequential-fan-out test below only exercises
a straightforward cache hit (the first mirror finishes and populates
`ReuploadCache` before the second even starts). The actual race
`ReuploadCache.get_or_create`'s single-flight/shield logic exists to close —
two independent tasks calling it for the same key *concurrently*, before
either's factory has completed — is exercised directly against the cache in
the second test below."""

import asyncio
import logging

from telethon.tl import types

from config import DirectionConfig
from telemirror.messagefilters._media import ReuploadCache
from telemirror.messagefilters.documentfilenamefilter import DocumentFilenameFilter
from telemirror.mirroring import EventProcessor
from telemirror.storage import InMemoryDatabase, MirrorMessage
from tests.conftest import make_message, run

SOURCE = -1001000000000
TARGET_A = -1002000000001
TARGET_B = -1002000000002


class _CountingClient:
    def __init__(self):
        self.download_calls = 0
        self.edits = []

    async def download_media(self, message, file):
        self.download_calls += 1
        with open(file, "wb") as f:
            f.write(b"data")

    async def upload_file(self, path, file_name=None):
        return "uploaded-handle"

    async def edit_message(self, entity, message, **kw):
        self.edits.append((entity, message))


def test_edit_message_reupload_runs_once_for_two_sequential_mirrors():
    db = run(InMemoryDatabase())
    run(db.insert_batch([
        MirrorMessage(5, SOURCE, 900, TARGET_A),
        MirrorMessage(5, SOURCE, 901, TARGET_B),
    ]))

    client = _CountingClient()
    # Both directions share the same DocumentFilenameFilter instance — the
    # exact scenario ReuploadCache's docstring says caching relies on.
    filters = DocumentFilenameFilter(suffix="Repost")
    cfg = DirectionConfig(disable_delete=False, disable_edit=False, filters=filters)

    proc = EventProcessor(
        chat_mapping={SOURCE: {TARGET_A: [cfg], TARGET_B: [cfg]}},
        database=db,
        client=client,
        logger=logging.getLogger("test.singleflight"),
    )

    media = types.MessageMediaDocument(
        document=types.Document(
            id=42, access_hash=0, file_reference=b"", date=None,
            mime_type="application/pdf", size=1024, dc_id=1,
            attributes=[types.DocumentAttributeFilename(file_name="lecture.pdf")],
        )
    )
    msg = make_message(media=media, channel_id=1000)
    msg.id = 5
    msg._client = client

    run(proc.edit_message(SOURCE, msg, "link"))

    assert client.download_calls == 1
    assert {entity for entity, _mid in client.edits} == {TARGET_A, TARGET_B}


def test_reupload_cache_single_flights_truly_concurrent_callers():
    """Two callers for the same key, launched together via `asyncio.gather`,
    both reach `get_or_create` before its `factory()` has run: `asyncio.gather`
    schedules both caller tasks before either runs, so the second caller's
    task is already queued ahead of the (only-just-created) factory task when
    the first caller yields at its `await asyncio.shield(inflight)` — the
    second caller therefore always finds `inflight` already set and shares it
    instead of starting its own factory call. This is the actual race
    `ReuploadCache.get_or_create`'s single-flight/shield logic exists for."""
    cache = ReuploadCache()
    call_count = 0

    async def factory():
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0)  # yield once, so this genuinely overlaps both awaiters
        return "uploaded"

    async def caller():
        return await cache.get_or_create(42, factory)

    async def scenario():
        return await asyncio.gather(caller(), caller())

    results = run(scenario())

    assert call_count == 1
    assert results == ["uploaded", "uploaded"]
