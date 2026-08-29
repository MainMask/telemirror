import os

from telethon.tl import types

from telemirror.messagefilters._media import downloaded_tempfile, filename_of
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
