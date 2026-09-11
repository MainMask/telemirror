"""Manual watermark-detection accuracy benchmark (not a pytest test).

Usage:
  python tests/watermark/benchmark_detection.py [<image_or_dir>] [--debug] [--threshold FLOAT]
  python tests/watermark/benchmark_detection.py
  python tests/watermark/benchmark_detection.py photo.jpg --debug
"""
import argparse
import os
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from telemirror.watermark.processor import ChannelWatermarkConfig, _run_detection

_DEFAULT_DATASET = str(Path(__file__).parent / "watermark_dataset")


def collect_files(path: str) -> list[str]:
    if os.path.isfile(path):
        return [path]
    files = [
        os.path.join(path, f) for f in os.listdir(path)
        if f.lower().endswith((".jpeg", ".png")) and "_detected" not in f
    ]
    return sorted(files, key=lambda p: (
        (0, int(os.path.splitext(os.path.basename(p))[0]))
        if os.path.splitext(os.path.basename(p))[0].isdigit()
        else (1, p)
    ))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default=_DEFAULT_DATASET)
    parser.add_argument("--threshold", type=float)
    parser.add_argument("--debug", action="store_true", help="Save *_detected.jpg with bbox")
    args = parser.parse_args()

    config = ChannelWatermarkConfig()
    if args.threshold is not None:
        config = ChannelWatermarkConfig(match_threshold=args.threshold)

    files = collect_files(args.path)
    if not files:
        sys.exit(f"No images found: {args.path}")

    found = total = 0
    for path in files:
        img = cv2.imread(path)
        if img is None:
            print(f"{os.path.basename(path)}: ERROR")
            continue
        total += 1
        h, w = img.shape[:2]

        score, scale, bbox = _run_detection(img, config)
        detected = bbox is not None
        if detected:
            found += 1

        bx, by, bw, bh = bbox if bbox else (0, 0, 0, 0)
        status = "FOUND " if detected else "MISSED"
        print(
            f"{os.path.basename(path):20s} ({w:4d}x{h:4d})  {status}"
            f"  score={score:.3f}  scale={scale:.2f}  bbox=({bx},{by},{bw},{bh})"
        )

        if args.debug:
            debug = img.copy()
            if bbox:
                cv2.rectangle(debug, (bx, by), (bx + bw, by + bh), (0, 255, 0), 2)
            cv2.imwrite(path.rsplit(".", 1)[0] + "_detected.jpg", debug)

    print(f"\nThreshold: {config.match_threshold:.2f}")
    if total > 1:
        print(f"Accuracy:  {found}/{total} ({found / total * 100:.0f}%)")


if __name__ == "__main__":
    main()
