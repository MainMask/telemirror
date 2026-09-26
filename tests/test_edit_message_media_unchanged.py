"""Pass 22: a caption-only edit must not re-process the media.

Every source edit used to re-run the re-uploading filters on the media: a
photo was re-downloaded and re-stamped at a new random spot, a video
re-encoded, a renamed document re-downloaded — and when that processing
failed, the stamped mirror photo was replaced by the unstamped original.
Each binding_id row now records the source media id it was produced from, and
`edit_message` sends `file=` only when the source media actually changed.
"""

import io
import logging
from types import SimpleNamespace

from PIL import Image
from telethon.tl import types

import telemirror.mirroring as mirroring
from config import DirectionConfig
from telemirror.messagefilters import EmptyMessageFilter, WatermarkRemovalFilter
from telemirror.mirroring import EventProcessor
from telemirror.storage import InMemoryDatabase, MirrorMessage
from tests.conftest import make_message, run

SOURCE = -1001000000000
TARGET = -1002000000001

_buf = io.BytesIO()
Image.new("RGB", (64, 48), "white").save(_buf, "JPEG")
JPEG = _buf.getvalue()


def _photo(photo_id):
    return types.MessageMediaPhoto(
        photo=types.Photo(
            id=photo_id, access_hash=0, file_reference=b"r", date=None,
            sizes=[], dc_id=1,
        )
    )


class _Client:
    def __init__(self, fail_download=False):
        self.fail_download = fail_download
        self.downloads = 0
        self.edits = []

    async def download_media(self, message, file=None, **kw):
        self.downloads += 1
        if self.fail_download:
            raise RuntimeError("DC hiccup")
        return JPEG

    async def upload_file(self, f, file_name=None, **kw):
        return types.InputFile(id=1, parts=1, name=file_name or "f", md5_checksum="")

    async def edit_message(self, entity, message, text=None, file=None, **kw):
        self.edits.append((text, type(file).__name__ if file is not None else None))


def _stamp():
    return WatermarkRemovalFilter(remove_watermark=False, stamp_watermark=True)


def _setup(client, rows, filters=None, db=None):
    db = db or run(InMemoryDatabase())
    run(db.insert_batch(rows))
    cfg = DirectionConfig(
        disable_delete=False, disable_edit=False, filters=filters or _stamp()
    )
    proc = EventProcessor(
        chat_mapping={SOURCE: {TARGET: [cfg]}},
        database=db,
        client=client,
        logger=logging.getLogger("test.editmedia"),
    )
    return db, proc


def _msg(client, text, photo_id, msg_id=1):
    m = make_message(text, media=_photo(photo_id))
    m.id = msg_id
    m._client = client
    m._chat = SimpleNamespace(noforwards=False)
    return m


def test_caption_only_edit_leaves_the_media_alone():
    # fail_download: if the media were touched at all, the stamped mirror
    # photo would be replaced by the unstamped original.
    client = _Client(fail_download=True)
    db, proc = _setup(client, [MirrorMessage(1, SOURCE, 900, TARGET, source_media_id=5)])

    run(proc.edit_message(SOURCE, _msg(client, "caption fixed", 5), "link"))

    assert client.downloads == 0
    assert client.edits == [("caption fixed", None)]


def test_replaced_media_is_processed_and_recorded():
    client = _Client()
    db, proc = _setup(client, [MirrorMessage(1, SOURCE, 900, TARGET, source_media_id=5)])

    run(proc.edit_message(SOURCE, _msg(client, "new photo", 6), "link"))

    assert client.downloads == 1
    assert client.edits == [("new photo", "InputFile")]
    assert [m.source_media_id for m in run(db.get_messages(1, SOURCE))] == [6]

    # The next caption-only edit of the new photo no longer touches it.
    run(proc.edit_message(SOURCE, _msg(client, "caption fixed", 6), "link"))
    assert client.downloads == 1
    assert client.edits[-1] == ("caption fixed", None)


def test_legacy_row_keeps_the_old_behaviour_and_learns_the_media_id():
    client = _Client()
    db, proc = _setup(client, [MirrorMessage(1, SOURCE, 900, TARGET)])

    run(proc.edit_message(SOURCE, _msg(client, "caption", 5), "link"))

    assert client.edits == [("caption", "InputFile")]
    assert [m.source_media_id for m in run(db.get_messages(1, SOURCE))] == [5]


def test_failed_db_update_is_logged_not_raised(caplog):
    class _BrokenUpdateDB(InMemoryDatabase):
        async def update_source_media_id(self, *args):
            raise RuntimeError("db down")

    client = _Client()
    _db, proc = _setup(
        client,
        [MirrorMessage(1, SOURCE, 900, TARGET, source_media_id=5)],
        db=run(_BrokenUpdateDB()),
    )

    with caplog.at_level(logging.ERROR, logger="test.editmedia"):
        run(proc.edit_message(SOURCE, _msg(client, "new photo", 6), "link"))

    assert client.edits == [("new photo", "InputFile")]
    assert "NOT recorded in DB" in caplog.text
    assert "Error while editing" not in caplog.text


def test_new_message_and_new_album_record_each_source_media_id(monkeypatch):
    async def fake_send_message(client, entity, message, **kw):
        return types.Message(id=900, peer_id=types.PeerChannel(1), message="")

    async def fake_send_file(client, entity, file, **kw):
        return [
            types.Message(id=910 + i, peer_id=types.PeerChannel(1), message="")
            for i in range(len(file))
        ]

    monkeypatch.setattr(mirroring, "send_message", fake_send_message)
    monkeypatch.setattr(mirroring, "send_file", fake_send_file)

    client = _Client()
    # No filters here: only the tracking is under test.
    db, proc = _setup(client, [], filters=EmptyMessageFilter())

    run(proc.new_message(SOURCE, _msg(client, "one", 5, msg_id=1), "link"))
    album = [_msg(client, "", 7, msg_id=2), _msg(client, "", 8, msg_id=3)]
    for m in album:
        m.grouped_id = 42
    run(proc.new_album(SOURCE, album, "link"))

    ids = {
        m.original_id: m.source_media_id
        for m in run(db.get_messages_batch([1, 2, 3], SOURCE))
    }
    assert ids == {1: 5, 2: 7, 3: 8}
