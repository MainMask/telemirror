"""WatermarkConfig: YAML scalars are coerced (numeric fields, bool toggles) and
the bundled reference template is optional (missing default → detection no-op)."""

import numpy as np
import pytest

from telemirror.watermark import processor
from telemirror.watermark.processor import WatermarkConfig


def test_string_values_coerced():
    c = WatermarkConfig(
        match_threshold="0.5",
        scale_min="0.3",
        scale_max="1",
        scale_steps="20",
        inpaint_dilate_px="4",
        stamp_opacity="0.6",
        stamp_scale="0.4",
    )
    assert (c.match_threshold, c.scale_min, c.scale_max) == (0.5, 0.3, 1.0)
    assert isinstance(c.scale_steps, int) and c.scale_steps == 20
    assert isinstance(c.inpaint_dilate_px, int) and c.inpaint_dilate_px == 4
    assert isinstance(c.stamp_opacity, float) and c.stamp_opacity == 0.6


def test_defaults_still_valid():
    c = WatermarkConfig()
    assert isinstance(c.match_threshold, float)
    assert isinstance(c.scale_steps, int)


def test_toggle_flags():
    assert WatermarkConfig().remove_watermark is True
    assert WatermarkConfig().stamp_watermark is True
    assert WatermarkConfig(remove_watermark=False).remove_watermark is False
    assert WatermarkConfig(stamp_watermark=False).stamp_watermark is False
    # quoted YAML scalar arrives as a string
    assert WatermarkConfig(remove_watermark="false").remove_watermark is False
    assert WatermarkConfig(stamp_watermark="no").stamp_watermark is False
    assert WatermarkConfig(stamp_watermark="true").stamp_watermark is True


def test_missing_default_template_disables_detection(monkeypatch):
    """The bundled reference watermark is optional: without it detection is a
    no-op (stamping still runs) instead of raising."""
    monkeypatch.setattr(processor.cv2, "imread", lambda *a, **k: None)
    processor._template_cache.pop(processor._DEFAULT_TEMPLATE, None)
    try:
        assert processor._load_template(processor._DEFAULT_TEMPLATE) is None
        img = np.zeros((80, 80, 3), dtype=np.uint8)
        assert processor._run_detection(img, WatermarkConfig()) == (0.0, 0.0, None)
    finally:
        processor._template_cache.pop(processor._DEFAULT_TEMPLATE, None)


def test_missing_explicit_template_still_raises():
    with pytest.raises(FileNotFoundError):
        processor._load_template("/no/such/watermark-template.png")
