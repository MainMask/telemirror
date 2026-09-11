"""S1-lite: WatermarkRemovalFilter must not download/process a video that exceeds
the re-upload limit — it forwards it unchanged."""

from telethon import events
from telethon.tl import types

from telemirror.messagefilters import WatermarkRemovalFilter
from telemirror.messagefilters._media import UPLOAD_LIMIT_BYTES
from tests.conftest import make_message, run

def _video_doc(size):
    return types.MessageMediaDocument(
        document=types.Document(
            id=1, access_hash=0, file_reference=b"", date=None,
            mime_type="video/mp4", size=size, dc_id=1,
            attributes=[types.DocumentAttributeVideo(duration=1, w=2, h=2)],
        )
    )


def test_oversize_video_left_untouched(monkeypatch):
    f = WatermarkRemovalFilter()

    async def boom(*a, **kw):
        raise AssertionError("_process_video must not run for an oversize file")

    monkeypatch.setattr(f, "_process_video", boom)

    media = _video_doc(UPLOAD_LIMIT_BYTES + 1)
    msg = make_message("", media=media, channel_id=1000)

    action, res = run(f._process_message(msg, events.NewMessage.Event))
    assert res.media is media  # unchanged
