import asyncio
import logging
import math
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_DEFAULT_TEMPLATE = str(Path(__file__).parent / "reference_watermark.png")

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

_template_cache: dict[str, tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]] = {}
_lama: Optional[object] = None


@dataclass(frozen=True)
class ChannelWatermarkConfig:
    template_path: str = _DEFAULT_TEMPLATE
    match_threshold: float = 0.33
    scale_min: float = 0.2
    scale_max: float = 1.0
    scale_steps: int = 80
    inpaint_dilate_px: int = 6


def _gradient_magnitude(gray: np.ndarray) -> np.ndarray:
    sx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    sy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.sqrt(sx ** 2 + sy ** 2)
    return cv2.normalize(mag, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)


def _load_template(path: str) -> tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]:
    if path not in _template_cache:
        raw = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if raw is None:
            raise FileNotFoundError(f"Watermark template not found: {path}")
        if raw.ndim == 3 and raw.shape[2] == 4:
            alpha = raw[:, :, 3]
            bgr = raw[:, :, :3]
        else:
            alpha = None
            bgr = raw
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        feat = _gradient_magnitude(gray)
        _template_cache[path] = (feat, gray, alpha)
    return _template_cache[path]


def _run_detection(
    image_bgr: np.ndarray,
    config: ChannelWatermarkConfig,
) -> tuple[float, float, Optional[tuple[int, int, int, int]]]:
    """Returns (score, scale, bbox) where bbox is None if score < match_threshold."""
    tmpl_feat, _tmpl_gray, _alpha = _load_template(config.template_path)
    img_gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    img_feat = _gradient_magnitude(img_gray)
    img_h, img_w = img_feat.shape
    tmpl_h, tmpl_w = tmpl_feat.shape

    min_scale_30pct = 0.30 * img_w / tmpl_w
    effective_min = max(config.scale_min, min_scale_30pct)
    scales = np.logspace(
        math.log10(effective_min),
        math.log10(config.scale_max),
        config.scale_steps,
    )

    best_val = -1.0
    best_scale = 0.0
    best_x = best_y = best_w = best_h = 0

    for s in scales:
        new_w = int(tmpl_w * s)
        new_h = int(tmpl_h * s)
        if new_w < 1 or new_h < 1 or new_w > img_w or new_h > img_h:
            continue
        resized = cv2.resize(tmpl_feat, (new_w, new_h))
        result = cv2.matchTemplate(img_feat, resized, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val > best_val:
            best_val = max_val
            best_scale = s
            best_x, best_y = max_loc
            best_w, best_h = new_w, new_h

    bbox = (best_x, best_y, best_w, best_h) if best_val >= config.match_threshold else None
    return best_val, best_scale, bbox


def _detect_watermark(
    image_bgr: np.ndarray,
    config: ChannelWatermarkConfig,
) -> Optional[tuple[int, int, int, int]]:
    _, _, bbox = _run_detection(image_bgr, config)
    return bbox


def _get_lama():
    global _lama
    if _lama is None:
        from simple_lama_inpainting import SimpleLama
        os.environ.setdefault("LAMA_DEVICE", "cpu")
        _lama = SimpleLama()
    return _lama


def remove_watermark_from_image(
    image_bytes: bytes,
    config: ChannelWatermarkConfig,
) -> Optional[bytes]:
    arr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        return None

    bbox = _detect_watermark(image, config)
    if bbox is None:
        return None

    x, y, w, h = bbox
    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    mask[y : y + h, x : x + w] = 255

    d = config.inpaint_dilate_px
    if d > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (d * 2 + 1, d * 2 + 1))
        mask = cv2.dilate(mask, kernel)

    image_pil = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    mask_pil = Image.fromarray(mask)

    result_pil = _get_lama()(image_pil, mask_pil)

    result_bgr = cv2.cvtColor(np.array(result_pil), cv2.COLOR_RGB2BGR)
    ok, buf = cv2.imencode(".jpg", result_bgr, [cv2.IMWRITE_JPEG_QUALITY, 92])
    if not ok:
        return None
    return buf.tobytes()


def remove_watermark_from_video(
    video_path: str,
    config: ChannelWatermarkConfig,
    output_path: str,
) -> bool:
    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * 0.1))
    ok, frame = cap.read()
    cap.release()

    if not ok or frame is None:
        logger.warning("Could not read sample frame from video: %s", video_path)
        return False

    bbox = _detect_watermark(frame, config)
    if bbox is None:
        return False

    fh, fw = frame.shape[:2]
    d = config.inpaint_dilate_px
    x, y, w, h = bbox
    x = max(0, x - d)
    y = max(0, y - d)
    w = min(fw - x, w + 2 * d)
    h = min(fh - y, h + 2 * d)

    delogo = f"delogo=x={x}:y={y}:w={w}:h={h}"
    cmd = ["ffmpeg", "-y", "-i", video_path, "-vf", delogo, "-c:a", "copy", output_path]
    proc = subprocess.run(cmd, capture_output=True, timeout=300)
    if proc.returncode != 0:
        logger.error(
            "ffmpeg delogo failed (code %d): %s",
            proc.returncode,
            proc.stderr.decode(errors="replace"),
        )
        return False
    return True


async def async_remove_watermark_from_image(
    image_bytes: bytes,
    config: ChannelWatermarkConfig,
) -> Optional[bytes]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, remove_watermark_from_image, image_bytes, config)


async def async_remove_watermark_from_video(
    video_path: str,
    config: ChannelWatermarkConfig,
    output_path: str,
) -> bool:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, remove_watermark_from_video, video_path, config, output_path)
