"""L2: numeric ChannelWatermarkConfig fields arrive as strings from YAML and must
be coerced before reaching numpy / an ffmpeg filtergraph."""

from telemirror.watermark.processor import ChannelWatermarkConfig


def test_string_values_coerced():
    c = ChannelWatermarkConfig(
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
    c = ChannelWatermarkConfig()
    assert isinstance(c.match_threshold, float)
    assert isinstance(c.scale_steps, int)
