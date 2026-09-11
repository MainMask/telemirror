"""stamp_watermark_on_video: the ffmpeg command carries the configured libx264
params and a timeout scaled to the clip length (existing filter tests mock the
whole call, so nothing else exercises the command build)."""

import asyncio

import pytest
from telethon.tl import types

import telemirror.messagefilters.watermarkfilter as wf
from telemirror.watermark import processor
from telemirror.watermark.processor import (
    WatermarkConfig,
    remove_watermark_from_video,
    stamp_watermark_on_video,
)
from tests.conftest import make_message, run


class _Cap:
    """cv2.VideoCapture stub: 1920x1080, 30 fps, 3600 frames → 120 s."""

    def __init__(self, *_a):
        pass

    def get(self, prop):
        return {
            processor.cv2.CAP_PROP_FRAME_WIDTH: 1920.0,
            processor.cv2.CAP_PROP_FRAME_HEIGHT: 1080.0,
            processor.cv2.CAP_PROP_FPS: 30.0,
            processor.cv2.CAP_PROP_FRAME_COUNT: 3600.0,
        }.get(prop, 0.0)

    def release(self):
        pass


class _Proc:
    returncode = 0


def _capture_cmd(monkeypatch):
    seen = {}

    def _fake_run(cmd, **kw):
        seen["cmd"] = cmd
        seen["timeout"] = kw["timeout"]
        return _Proc()

    monkeypatch.setattr(processor.cv2, "VideoCapture", _Cap)
    monkeypatch.setattr(processor.subprocess, "run", _fake_run)
    return seen


def test_ffmpeg_command_uses_configured_codec_params(monkeypatch):
    seen = _capture_cmd(monkeypatch)
    config = WatermarkConfig(stamp_video_preset="faster", stamp_video_crf="20")

    assert stamp_watermark_on_video("in.mp4", config, "out.mp4") is True

    cmd = seen["cmd"]
    assert cmd[cmd.index("-c:v") + 1] == "libx264"
    assert cmd[cmd.index("-preset") + 1] == "faster"
    assert cmd[cmd.index("-crf") + 1] == "20"
    assert cmd[cmd.index("-pix_fmt") + 1] == "yuv420p"
    assert cmd[cmd.index("-c:a") + 1] == "copy"


def test_ffmpeg_timeout_scales_with_duration(monkeypatch):
    seen = _capture_cmd(monkeypatch)
    stamp_watermark_on_video("in.mp4", WatermarkConfig(), "out.mp4")
    # 120 s clip → max(300, 120*4 + 120) = 600
    assert seen["timeout"] == 600.0


def test_bad_preset_rejected_at_config_time():
    with pytest.raises(ValueError, match="x264 preset"):
        WatermarkConfig(stamp_video_preset="fastest")


def test_zero_max_concurrent_video_encodes_rejected_at_config_time():
    """0 would make every `async with semaphore:` block forever (Pass 14) —
    reject it at config time instead of hanging the pipeline silently."""
    with pytest.raises(ValueError, match="max_concurrent_video_encodes"):
        WatermarkConfig(max_concurrent_video_encodes=0)


def test_remove_watermark_timeout_scales_with_duration(monkeypatch):
    """`remove_watermark_from_video`'s delogo re-encode is not cheaper than the
    stamp step (no `-c:v copy`), so it must use the same duration-scaled budget
    instead of a flat 300s that a long clip's real ffmpeg run can outlast (see
    deploy/README.md's measured 6-13 min stamp time on the production host)."""
    seen = _capture_cmd(monkeypatch)
    monkeypatch.setattr(_Cap, "set", lambda self, prop, value: None, raising=False)

    class _Frame:
        shape = (1080, 1920)  # fh, fw

    monkeypatch.setattr(_Cap, "read", lambda self: (True, _Frame()), raising=False)
    monkeypatch.setattr(processor, "_detect_watermark", lambda frame, config: (10, 10, 50, 20))

    assert remove_watermark_from_video("in.mp4", WatermarkConfig(), "out.mp4") is True
    # 120 s clip (3600 frames / 30 fps) → max(300, 120*4 + 120) = 600
    assert seen["timeout"] == 600.0


# ── max_concurrent_video_encodes (Pass 13) ──────────────────────────────────
# On a 1 vCPU host, several concurrent ffmpeg encodes don't run faster — they
# only multiply peak RSS inside the same systemd MemoryMax cgroup. The
# semaphore in watermarkfilter.py must actually bound concurrency, not just
# happen to look serial for an unrelated reason.

class _EncodeClient:
    async def download_media(self, message, file):
        return b"raw"

    async def upload_file(self, data, file_name=None):
        return "HANDLE"


def _encode_video_message(doc_id):
    media = types.MessageMediaDocument(
        document=types.Document(
            id=doc_id, access_hash=0, file_reference=b"", date=None,
            mime_type="video/mp4", size=1024, dc_id=1,
            attributes=[types.DocumentAttributeVideo(duration=1, w=2, h=2)],
        )
    )
    msg = make_message(media=media, channel_id=1000)
    msg._client = _EncodeClient()
    return msg


def _tracking_stamp(monkeypatch, state):
    async def _stamp(src, config, out):
        state["in_flight"] += 1
        state["max_seen"] = max(state["max_seen"], state["in_flight"])
        await asyncio.sleep(0.01)
        state["in_flight"] -= 1
        return True

    monkeypatch.setattr(wf, "async_stamp_watermark_on_video", _stamp)


def test_concurrent_video_encodes_are_serialized(monkeypatch):
    monkeypatch.setattr(wf, "_video_encode_semaphore", None)
    monkeypatch.setattr(wf, "_video_encode_semaphore_limit", None)
    state = {"in_flight": 0, "max_seen": 0}
    _tracking_stamp(monkeypatch, state)

    f = wf.WatermarkRemovalFilter(
        remove_watermark=False, max_concurrent_video_encodes=1
    )
    msg1, msg2 = _encode_video_message(1), _encode_video_message(2)

    async def both():
        await asyncio.gather(
            f._process_video(msg1, f._config, msg1.media.document),
            f._process_video(msg2, f._config, msg2.media.document),
        )

    run(both())
    assert state["max_seen"] == 1


def test_max_concurrent_video_encodes_raises_the_cap(monkeypatch):
    monkeypatch.setattr(wf, "_video_encode_semaphore", None)
    monkeypatch.setattr(wf, "_video_encode_semaphore_limit", None)
    state = {"in_flight": 0, "max_seen": 0}
    _tracking_stamp(monkeypatch, state)

    f = wf.WatermarkRemovalFilter(
        remove_watermark=False, max_concurrent_video_encodes=2
    )
    msg1, msg2 = _encode_video_message(1), _encode_video_message(2)

    async def both():
        await asyncio.gather(
            f._process_video(msg1, f._config, msg1.media.document),
            f._process_video(msg2, f._config, msg2.media.document),
        )

    run(both())
    assert state["max_seen"] == 2


def test_mismatched_limit_logs_a_warning_instead_of_silently_ignoring_it(
    monkeypatch, caplog
):
    """The cap is process-wide, not per-direction (Pass 14): whichever config
    is seen first wins silently unless a later, differently-configured call
    is at least logged so an operator can notice."""
    monkeypatch.setattr(wf, "_video_encode_semaphore", None)
    monkeypatch.setattr(wf, "_video_encode_semaphore_limit", None)

    with caplog.at_level("WARNING", logger="telemirror.messagefilters.watermarkfilter"):
        first = wf._get_video_encode_semaphore(1)
        second = wf._get_video_encode_semaphore(3)

    assert first is second  # still the same, process-wide semaphore
    assert any("ignored" in r.message for r in caplog.records)
