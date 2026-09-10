"""estimate_stamp_encode_s: rough re-encode wall-clock, scaled from a measured
1080p baseline by resolution; guards against zero/negative inputs."""

import pytest

from telemirror.watermark.processor import estimate_stamp_encode_s

_RATIO = 0.73  # default stamp_video_encode_realtime_ratio


def test_1080p_baseline():
    # (1920*1080 / 1920*1080) * 100 / 0.73 ≈ 137s
    assert estimate_stamp_encode_s(1920, 1080, 100, _RATIO) == pytest.approx(100 / _RATIO)


def test_4k_scales_by_pixel_ratio():
    hd = estimate_stamp_encode_s(1920, 1080, 100, _RATIO)
    uhd = estimate_stamp_encode_s(3840, 2160, 100, _RATIO)
    assert uhd == pytest.approx(4 * hd)


def test_non_positive_inputs_return_zero():
    assert estimate_stamp_encode_s(1920, 1080, 100, 0) == 0.0
    assert estimate_stamp_encode_s(1920, 1080, 100, -1) == 0.0
    assert estimate_stamp_encode_s(0, 1080, 100, _RATIO) == 0.0
    assert estimate_stamp_encode_s(1920, 0, 100, _RATIO) == 0.0
    assert estimate_stamp_encode_s(1920, 1080, 0, _RATIO) == 0.0
