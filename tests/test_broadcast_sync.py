"""P1+P2: startup broadcast sync must be idempotent (no edit-storm on restart)
and must not materialize the whole channel history."""

import datetime
import logging

from telethon.tl import types

from telemirror.mirroring import Mirroring
from telemirror.storage import InMemoryDatabase
from tests.conftest import run

BC = -1001111111111
_PEER = 1111111111


def _msg(mid, edit_ts=None, grouped_id=None):
    return types.Message(
        id=mid,
        peer_id=types.PeerChannel(_PEER),
        message=f"m{mid}",
        edit_date=(
            datetime.datetime.fromtimestamp(edit_ts, datetime.timezone.utc)
            if edit_ts
            else None
        ),
        grouped_id=grouped_id,
    )


class FakeClient:
    """Serves messages as a streaming async iterator (never a list)."""

    def __init__(self, messages):
        self._messages = messages

    def iter_messages(self, entity, reverse=False):
        ordered = sorted(self._messages, key=lambda m: m.id, reverse=not reverse)

        async def gen():
            for m in ordered:
                yield m

        return gen()


class RecProcessor:
    def __init__(self):
        self.calls = []

    async def new_message(self, chat, msg, link):
        self.calls.append(("new", msg.id))

    async def new_album(self, chat, album, link):
        self.calls.append(("new_album", tuple(m.id for m in album)))

    async def edit_message(self, chat, msg, link):
        self.calls.append(("edit", msg.id))

    async def delete_message(self, chat, ids):
        self.calls.append(("delete", tuple(sorted(ids))))


def _mirroring(db, messages):
    m = Mirroring(
        chat_mapping={BC: {}},
        database=db,
        receiver=object(),
        sender=object(),
        logger=logging.getLogger("test"),
        broadcast_channel=BC,
    )
    m._processor = RecProcessor()
    return m, FakeClient(messages)


def _sync(db, messages):
    m, client = _mirroring(db, messages)
    run(m._sync_broadcast_channel(client))
    return m._processor.calls


def test_first_sync_sends_all_and_records():
    db = run(InMemoryDatabase())
    calls = _sync(db, [_msg(1), _msg(2), _msg(3)])
    assert calls == [("new", 1), ("new", 2), ("new", 3)]
    assert set(run(db.get_broadcast_sync(BC))) == {1, 2, 3}


def test_restart_is_a_noop():
    db = run(InMemoryDatabase())
    _sync(db, [_msg(1), _msg(2)])
    assert _sync(db, [_msg(1), _msg(2)]) == []


def test_edit_only_when_edit_date_advances():
    db = run(InMemoryDatabase())
    _sync(db, [_msg(1, edit_ts=1000)])
    assert _sync(db, [_msg(1, edit_ts=1000)]) == []  # same edit ts
    assert _sync(db, [_msg(1, edit_ts=2000)]) == [("edit", 1)]  # newer


def test_new_message_after_previous_sync():
    db = run(InMemoryDatabase())
    _sync(db, [_msg(1), _msg(2)])
    assert _sync(db, [_msg(1), _msg(2), _msg(3)]) == [("new", 3)]


def test_deleted_source_message_is_removed():
    db = run(InMemoryDatabase())
    _sync(db, [_msg(1), _msg(2), _msg(3)])
    calls = _sync(db, [_msg(1), _msg(3)])
    assert ("delete", (2,)) in calls
    assert set(run(db.get_broadcast_sync(BC))) == {1, 3}


def test_albums_are_grouped():
    db = run(InMemoryDatabase())
    calls = _sync(db, [_msg(1, grouped_id=99), _msg(2, grouped_id=99), _msg(3)])
    assert ("new_album", (1, 2)) in calls
    assert ("new", 3) in calls
