"""WatermarkRemovalFilter global toggles: remove_watermark (detection/inpainting)
and stamp_watermark (own watermark) can each be turned off; an optional `channels`
list narrows which sources are processed."""

from datetime import datetime, timezone

from telethon import events
from telethon.tl import types

import telemirror.messagefilters.watermarkfilter as wf
from tests.conftest import make_message, run

CHAT_ID = -1000000001000  # == chat_id of make_message(channel_id=1000)


class _Client:
    def __init__(self):
        self.uploaded = None
        self.downloaded = 0

    async def download_media(self, message, file):
        self.downloaded += 1
        return b"rawphoto"

    async def upload_file(self, data, file_name=None):
        self.uploaded = data
        return "HANDLE"


def _photo_message(client):
    media = types.MessageMediaPhoto(
        photo=types.Photo(
            id=99, access_hash=1, file_reference=b"x",
            date=datetime.now(timezone.utc), sizes=[], dc_id=1,
        )
    )
    msg = make_message(media=media, channel_id=1000)
    msg._client = client
    return msg


def _video_message(client):
    media = types.MessageMediaDocument(
        document=types.Document(
            id=77, access_hash=0, file_reference=b"", date=None,
            mime_type="video/mp4", size=1024, dc_id=1,
            attributes=[types.DocumentAttributeVideo(duration=1, w=2, h=2)],
        )
    )
    msg = make_message(media=media, channel_id=1000)
    msg._client = client
    return msg


def _spies(monkeypatch, remove_result=None):
    calls = {"remove": 0, "stamp": 0}

    async def _remove(*a, **k):
        calls["remove"] += 1
        return remove_result

    async def _stamp(data, config):
        calls["stamp"] += 1
        return b"stamped"

    monkeypatch.setattr(wf, "async_remove_watermark_from_image", _remove)
    monkeypatch.setattr(wf, "async_stamp_watermark_on_image", _stamp)
    return calls


def _video_spies(monkeypatch, removed=False):
    calls = {"remove": 0, "stamp": 0}

    async def _remove(src, config, out):
        calls["remove"] += 1
        return removed

    async def _stamp(src, config, out):
        calls["stamp"] += 1
        return True

    monkeypatch.setattr(wf, "async_remove_watermark_from_video", _remove)
    monkeypatch.setattr(wf, "async_stamp_watermark_on_video", _stamp)
    return calls


def _run(flags, message, **kw):
    f = wf.WatermarkRemovalFilter(**flags, **kw)
    return run(f._process_message(message, events.NewMessage.Event))


# ── remove_watermark toggle ──────────────────────────────────────────────────

def test_stamp_only_skips_detection(monkeypatch):
    calls = _spies(monkeypatch)
    client = _Client()
    _, res = _run({"remove_watermark": False}, _photo_message(client))
    assert calls == {"remove": 0, "stamp": 1}
    assert client.uploaded == b"stamped"
    assert res.media == "HANDLE"


def test_default_runs_detection(monkeypatch):
    calls = _spies(monkeypatch)
    _run({}, _photo_message(_Client()))
    assert calls == {"remove": 1, "stamp": 1}


def test_video_stamp_only_skips_detection(monkeypatch):
    calls = _video_spies(monkeypatch)
    _, res = _run({"remove_watermark": False}, _video_message(_Client()))
    assert calls == {"remove": 0, "stamp": 1}
    assert res.media == "HANDLE"


def test_video_default_runs_detection(monkeypatch):
    calls = _video_spies(monkeypatch)
    _run({}, _video_message(_Client()))
    assert calls == {"remove": 1, "stamp": 1}


# ── stamp_watermark toggle ───────────────────────────────────────────────────

def test_removal_only_skips_stamp(monkeypatch):
    calls = _spies(monkeypatch, remove_result=b"cleaned")
    client = _Client()
    _, res = _run({"stamp_watermark": False}, _photo_message(client))
    assert calls == {"remove": 1, "stamp": 0}
    assert client.uploaded == b"cleaned"
    assert res.media == "HANDLE"


def test_removal_only_nothing_found_is_noop(monkeypatch):
    calls = _spies(monkeypatch, remove_result=None)
    client = _Client()
    _, res = _run({"stamp_watermark": False}, _photo_message(client))
    assert calls == {"remove": 1, "stamp": 0}
    assert client.uploaded is None
    assert isinstance(res.media, types.MessageMediaPhoto)  # unchanged


def test_video_removal_only_skips_stamp(monkeypatch):
    calls = _video_spies(monkeypatch, removed=True)
    _, res = _run({"stamp_watermark": False}, _video_message(_Client()))
    assert calls == {"remove": 1, "stamp": 0}
    assert res.media == "HANDLE"


# ── both off ─────────────────────────────────────────────────────────────────

def test_both_disabled_skips_download(monkeypatch):
    calls = _spies(monkeypatch)
    client = _Client()
    _, res = _run(
        {"remove_watermark": False, "stamp_watermark": False}, _photo_message(client)
    )
    assert calls == {"remove": 0, "stamp": 0}
    assert client.downloaded == 0
    assert isinstance(res.media, types.MessageMediaPhoto)  # unchanged


# ── channels narrowing ───────────────────────────────────────────────────────

def test_channels_list_limits_processing(monkeypatch):
    calls = _spies(monkeypatch)
    client = _Client()
    # message is from channel 1000 (CHAT_ID); filter only watches another id
    _, res = _run({}, _photo_message(client), channels=[-1009999999999])
    assert calls == {"remove": 0, "stamp": 0}
    assert client.downloaded == 0
    assert isinstance(res.media, types.MessageMediaPhoto)  # unchanged


def test_channels_list_includes_source(monkeypatch):
    calls = _spies(monkeypatch)
    _, res = _run({}, _photo_message(_Client()), channels=[CHAT_ID])
    assert calls == {"remove": 1, "stamp": 1}
    assert res.media == "HANDLE"
