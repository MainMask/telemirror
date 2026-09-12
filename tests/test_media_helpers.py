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


def _retry_msg(client, media=None):
    class Msg:
        _client = client
        chat_id = -1001234567890
        id = 42

    msg = Msg()
    msg.media = media
    return msg


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


def test_download_retry_refreshes_file_reference_and_succeeds(monkeypatch):
    _no_sleep(monkeypatch)
    calls = {"n": 0}

    class FakeClient:
        async def download_media(self, message, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise errors.FileReferenceExpiredError(request=None)
            return b"payload"

        async def get_messages(self, chat_id, ids):
            return _retry_msg(self, media=object())

    assert run(download_media_with_retry(_retry_msg(FakeClient()), file=bytes)) == b"payload"
    assert calls["n"] == 2


def test_download_retry_refreshes_on_last_attempt(monkeypatch):
    """A FileReferenceExpiredError on the very last retry attempt must still
    refresh and succeed inline — not fall off the end of the for-loop with no
    remaining iteration to retry in, which silently returned None."""
    _no_sleep(monkeypatch)
    calls = {"n": 0}
    attempts = len(_media._DOWNLOAD_RETRY_DELAYS) + 1

    class FakeClient:
        async def download_media(self, message, **kwargs):
            calls["n"] += 1
            if calls["n"] < attempts:
                raise ValueError("Request was unsuccessful 6 time(s)")
            if calls["n"] == attempts:
                raise errors.FileReferenceExpiredError(request=None)
            return b"payload"

        async def get_messages(self, chat_id, ids):
            return _retry_msg(self, media=object())

    result = run(download_media_with_retry(_retry_msg(FakeClient()), file=bytes))
    assert result == b"payload"
    assert calls["n"] == attempts + 1


def test_download_retry_transient_error_after_refresh_uses_remaining_schedule(monkeypatch):
    """A transient error on the retry right after a file_reference refresh must
    not immediately give up as MediaDownloadError — it should fall back to
    whatever's left of the normal spaced-retry schedule and can still
    succeed."""
    _no_sleep(monkeypatch)
    calls = {"n": 0}

    class FakeClient:
        async def download_media(self, message, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise errors.FileReferenceExpiredError(request=None)
            if calls["n"] == 2:
                raise ConnectionError("dc hiccup right after refresh")
            return b"payload"

        async def get_messages(self, chat_id, ids):
            return _retry_msg(self, media=object())

    result = run(download_media_with_retry(_retry_msg(FakeClient()), file=bytes))
    assert result == b"payload"
    assert calls["n"] == 3


def test_download_retry_second_file_reference_expired_raises(monkeypatch):
    """A second FileReferenceExpiredError (after the one-shot refresh) must
    raise MediaDownloadError, not the raw error: a strict_media_mode caller's
    `except MediaDownloadError: raise` guard only catches this class, and a
    raw FileReferenceExpiredError would fall through to a bare `except
    Exception` and silently degrade instead of preserving the checkpoint."""
    _no_sleep(monkeypatch)
    calls = {"n": 0}

    class FakeClient:
        async def download_media(self, message, **kwargs):
            calls["n"] += 1
            raise errors.FileReferenceExpiredError(request=None)

        async def get_messages(self, chat_id, ids):
            return _retry_msg(self, media=object())

    with pytest.raises(MediaDownloadError):
        run(download_media_with_retry(_retry_msg(FakeClient()), file=bytes))
    assert calls["n"] == 2  # original attempt + one refreshed retry, no more


def test_download_retry_refresh_finds_source_gone_raises_media_download_error(monkeypatch):
    """A refresh that can't find the source message (deleted, or no media)
    must also raise MediaDownloadError, for the same strict_media_mode reason
    as the second-expiry case above."""
    _no_sleep(monkeypatch)

    class FakeClient:
        async def download_media(self, message, **kwargs):
            raise errors.FileReferenceExpiredError(request=None)

        async def get_messages(self, chat_id, ids):
            return None

    with pytest.raises(MediaDownloadError):
        run(download_media_with_retry(_retry_msg(FakeClient()), file=bytes))


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
