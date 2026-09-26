"""Pass 23, third review: Telethon dispatches `events.Album` only after its
album delay (1.01 s here), while `MessageEdited`/`MessageDeleted` arrive at
once. An edit or delete landing in that window found no rows and no in-flight
fan-out, and was dropped: the album was then mirrored with the old caption
(or left orphaned after its source was deleted)."""

import asyncio
import datetime
import logging

import pytest
from telethon.tl import types

import telemirror.mirroring as mirroring
from config import DirectionConfig
from telemirror.messagefilters import EmptyMessageFilter
from telemirror.mirroring import EventProcessor
from telemirror.storage import InMemoryDatabase
from tests.conftest import run

SOURCE = -1001000000001
TARGET = -1001000000002
ALBUM_DELAY = 0.1  # stands in for the real 1.01 s


class _Client:
    def __init__(self):
        self.edited: list[str] = []
        self.deleted: list[int] = []

    async def edit_message(self, **kw):
        self.edited.append(kw["text"])

    async def delete_messages(self, entity, message_ids):
        self.deleted.extend(message_ids)


@pytest.fixture
def fake_send(monkeypatch):
    async def fake_send_file(client, entity, caption, file, **kw):
        return [
            types.Message(id=900 + i, peer_id=types.PeerChannel(2), message=c)
            for i, c in enumerate(caption)
        ]

    monkeypatch.setattr(mirroring, "send_file", fake_send_file)
    monkeypatch.setattr(mirroring, "_ALBUM_EVENT_GRACE_SEC", ALBUM_DELAY * 2, raising=False)


def _item(i, text, age_sec=0.0):
    return types.Message(
        id=i, peer_id=types.PeerChannel(1000000001), message=text, grouped_id=7,
        date=datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(seconds=age_sec),
        media=types.MessageMediaPhoto(photo=types.PhotoEmpty(id=i)),
    )


def _processor(db, client, disable_delete=False):
    cfg = DirectionConfig(
        disable_delete=disable_delete, disable_edit=False, filters=EmptyMessageFilter()
    )
    return EventProcessor({SOURCE: {TARGET: [cfg]}}, db, client, logging.getLogger("t"))


def _race(proc, early_event):
    """The album event after ALBUM_DELAY; `early_event` right away."""
    album = [_item(1, "old caption"), _item(2, "")]

    async def album_event():
        await asyncio.sleep(ALBUM_DELAY)
        await proc.new_album(SOURCE, album, "link")

    async def scenario():
        await asyncio.gather(album_event(), early_event())

    run(scenario())


def test_album_edit_before_the_album_event_reaches_the_mirror(fake_send):
    client = _Client()
    proc = _processor(run(InMemoryDatabase()), client)
    _race(proc, lambda: proc.edit_message(SOURCE, _item(1, "NEW caption"), "link"))
    assert client.edited == ["NEW caption"]


def test_album_delete_before_the_album_event_reaches_the_mirror(fake_send):
    client = _Client()
    proc = _processor(run(InMemoryDatabase()), client)
    _race(proc, lambda: proc.delete_message(SOURCE, [1, 2]))
    assert sorted(client.deleted) == [900, 901]


def _sleeps(monkeypatch):
    calls: list[float] = []
    real_sleep = asyncio.sleep

    async def spy(delay, *a, **kw):
        calls.append(delay)
        return await real_sleep(0)

    monkeypatch.setattr(mirroring.asyncio, "sleep", spy)
    return calls


def test_old_album_item_without_rows_does_not_wait(fake_send, monkeypatch):
    """E.g. a `_sync_broadcast_channel` catch-up edit of an unmirrored item."""
    proc = _processor(run(InMemoryDatabase()), _Client())
    calls = _sleeps(monkeypatch)
    run(proc.edit_message(SOURCE, _item(1, "text", age_sec=3600), "link"))
    assert calls == []


def test_delete_does_not_wait_when_every_direction_disables_deletes(fake_send, monkeypatch):
    """The live donors (`disable_delete: true`) never pay the grace wait."""
    proc = _processor(run(InMemoryDatabase()), _Client(), disable_delete=True)
    calls = _sleeps(monkeypatch)
    run(proc.delete_message(SOURCE, [1]))
    assert calls == []
