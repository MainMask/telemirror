"""past_mode's give-up-on-a-stuck-message logic must not drop earlier album
siblings: when an album fails to download, giving up must advance the
checkpoint past the WHOLE album (its max id), not just the one item that
happened to fail to download. Since resume uses an exclusive `min_id`, a
checkpoint landing on an interior/lower id would leave any sibling with a
LOWER id permanently unreachable on resume, even though the whole album's
send for that direction failed together (none of its members were actually
mirrored)."""

import logging

from telethon.tl import types

import past_mode
from config import DirectionConfig, PastModeConfig
from telemirror.messagefilters import EmptyMessageFilter, MediaDownloadError
from telemirror.storage import InMemoryDatabase
from tests.conftest import run

SRC = -1001111111111
TGT = -1002222222222
_LOG = logging.getLogger("test.past_mode.albumcheckpoint")


def _cfg(pm: PastModeConfig) -> DirectionConfig:
    return DirectionConfig(
        disable_delete=False,
        disable_edit=False,
        filters=EmptyMessageFilter(),
        past_mode=pm,
    )


class _Total:
    def __init__(self, n):
        self.total = n


class _AlbumClient:
    """One album: ids 100 (lower) and 102 (higher), same grouped_id."""

    def __init__(self):
        self._messages = [
            types.Message(id=100, peer_id=types.PeerChannel(1), message="a", grouped_id=7),
            types.Message(id=102, peer_id=types.PeerChannel(1), message="b", grouped_id=7),
        ]

    async def get_messages(self, entity, limit=None, **kw):
        return _Total(len(self._messages))

    def iter_messages(self, entity, limit=None, reverse=False, min_id=None, **kw):
        msgs = [m for m in self._messages if min_id is None or m.id > min_id]
        if not reverse:
            msgs = list(reversed(msgs))

        async def gen():
            for m in msgs:
                yield m

        return gen()


class _AlwaysFailsOnAlbum:
    def __init__(self, **kw):
        pass

    async def new_message(self, chat, msg, link):
        pass

    async def new_album(self, chat, album, link):
        # The album's lower/first id is the one that fails to download —
        # same as messagefilters/_media.py attaching whichever single item's
        # id was being downloaded when its own retries ran out.
        raise MediaDownloadError("t.me/c/1/100: exhausted", message_id=album[0].id)


def test_give_up_on_stuck_album_advances_checkpoint_past_whole_album(monkeypatch):
    async def fake_sleep(seconds):
        pass

    notified = []

    async def fake_notify(client, src, mid, log):
        notified.append(mid)

    monkeypatch.setattr(past_mode.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(past_mode, "_notify_skipped", fake_notify)
    monkeypatch.setattr(past_mode, "EventProcessor", _AlwaysFailsOnAlbum)

    db = run(InMemoryDatabase())

    run(
        past_mode._replay_with_retry(
            _AlbumClient(), db, SRC, TGT,
            [_cfg(PastModeConfig(full_history=True, send_delay=0))], _LOG,
        )
    )

    # Checkpoint lands on the album's MAX id (102), matching what the
    # success path would have used (`album[-1].id`) — not 100, the one item
    # that happened to fail, which would otherwise leave 100 permanently
    # excluded on resume (min_id is exclusive) despite never having actually
    # been mirrored.
    assert run(db.get_past_mode_checkpoint(SRC, TGT)) == 102
    # The skip notification must name the item that actually failed to
    # download (100), not the checkpoint-advancement id (102) — an operator
    # following the alert's link needs to find the broken file, not a
    # message that sent fine.
    assert notified == [100]
