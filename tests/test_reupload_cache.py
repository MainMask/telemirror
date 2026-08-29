import time

from telemirror.messagefilters._media import ReuploadCache, source_media_id
from telethon.tl import types


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
