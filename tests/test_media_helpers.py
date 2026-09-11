import asyncio
import os

import pytest
from telethon import errors
from telethon.tl import types

from telemirror.messagefilters import _media
from telemirror.messagefilters._media import (
    MediaDownloadError,
    download_media_with_retry,
    downloaded_tempfile,
    filename_of,
)
from tests.conftest import run


def _doc(*attrs):
    return types.Document(
        id=1, access_hash=0, file_reference=b"", date=None, mime_type="x",
        size=1, dc_id=1, attributes=list(attrs),
    )


def test_filename_of_found():
    doc = _doc(
        types.DocumentAttributeAnimated(),
        types.DocumentAttributeFilename(file_name="report.pdf"),
    )
    assert filename_of(doc) == "report.pdf"


def test_filename_of_absent():
    assert filename_of(_doc(types.DocumentAttributeAnimated())) is None


def test_downloaded_tempfile_cleans_up():
    class FakeClient:
        async def download_media(self, message, file):
            with open(file, "wb") as f:
                f.write(b"data")

    class Msg:
        _client = FakeClient()

    seen = {}

    async def go():
        async with downloaded_tempfile(Msg(), suffix=".bin") as path:
            seen["path"] = path
            assert os.path.exists(path)
            assert path.endswith(".bin")

    run(go())
    assert not os.path.exists(seen["path"])


def test_downloaded_tempfile_cleans_up_on_error():
    class FakeClient:
        async def download_media(self, message, file):
            pass

    class Msg:
        _client = FakeClient()

    seen = {}

    async def go():
        async with downloaded_tempfile(Msg()) as path:
            seen["path"] = path
            raise RuntimeError("boom")

    try:
        run(go())
    except RuntimeError:
        pass
    assert not os.path.exists(seen["path"])


def _retry_msg(client):
    class Msg:
        _client = client
        chat_id = -1001234567890
        id = 42

    return Msg()


def _no_sleep(monkeypatch):
    async def instant(_delay):
        pass

    monkeypatch.setattr(_media.asyncio, "sleep", instant)


def test_download_retry_succeeds_after_transient_failures(monkeypatch):
    _no_sleep(monkeypatch)
    calls = {"n": 0}

    class FakeClient:
        async def download_media(self, message, **kwargs):
            calls["n"] += 1
            if calls["n"] < 3:
                raise (asyncio.TimeoutError() if calls["n"] == 1
                       else ValueError("Request was unsuccessful 6 time(s)"))
            return b"payload"

    assert run(download_media_with_retry(_retry_msg(FakeClient()), file=bytes)) == b"payload"
    assert calls["n"] == 3


def test_download_retry_exhausts_and_raises_media_download_error(monkeypatch):
    _no_sleep(monkeypatch)
    calls = {"n": 0}
    original = ConnectionError("dc down")

    class FakeClient:
        async def download_media(self, message, **kwargs):
            calls["n"] += 1
            raise original

    with pytest.raises(MediaDownloadError) as excinfo:
        run(download_media_with_retry(_retry_msg(FakeClient()), file=bytes))
    assert calls["n"] == len(_media._DOWNLOAD_RETRY_DELAYS) + 1
    assert excinfo.value.__cause__ is original
    assert excinfo.value.message_id == 42  # from _retry_msg


def test_download_retry_reraises_non_transient_valueerror(monkeypatch):
    _no_sleep(monkeypatch)
    calls = {"n": 0}

    class FakeClient:
        async def download_media(self, message, **kwargs):
            calls["n"] += 1
            raise ValueError("bad file argument")

    with pytest.raises(ValueError, match="bad file argument"):
        run(download_media_with_retry(_retry_msg(FakeClient()), file=bytes))
    assert calls["n"] == 1  # deterministic failure — no retry


def test_download_retry_does_not_swallow_floodwait(monkeypatch):
    _no_sleep(monkeypatch)
    calls = {"n": 0}

    class FakeClient:
        async def download_media(self, message, **kwargs):
            calls["n"] += 1
            raise errors.FloodWaitError(request=None)

    with pytest.raises(errors.FloodWaitError):
        run(download_media_with_retry(_retry_msg(FakeClient()), file=bytes))
    assert calls["n"] == 1  # propagated immediately, no retry


def test_downloaded_tempfile_retries_then_yields(monkeypatch):
    _no_sleep(monkeypatch)
    calls = {"n": 0}

    class FakeClient:
        async def download_media(self, message, file):
            calls["n"] += 1
            if calls["n"] == 1:
                raise asyncio.TimeoutError()
            with open(file, "wb") as f:
                f.write(b"data")

    class Msg:
        _client = FakeClient()
        chat_id = -1001234567890
        id = 7

    seen = {}

    async def go():
        async with downloaded_tempfile(Msg(), suffix=".bin") as path:
            seen["path"] = path
            assert os.path.exists(path)

    run(go())
    assert calls["n"] == 2
    assert not os.path.exists(seen["path"])
