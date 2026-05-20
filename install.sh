#!/usr/bin/env bash
set -e

# simple-lama-inpainting pins pillow<10 which doesn't build on Python 3.12+.
# Install it without its broken dependency metadata, then install everything else normally.
pip install simple-lama-inpainting --no-deps
pip install -r requirements.txt
