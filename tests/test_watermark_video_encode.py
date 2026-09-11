"""stamp_watermark_on_video: the ffmpeg command carries the configured libx264
params and a timeout scaled to the clip length (existing filter tests mock the
whole call, so nothing else exercises the command build)."""

import pytest

from telemirror.watermark import processor
from telemirror.watermark.processor import WatermarkConfig, stamp_watermark_on_video


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
