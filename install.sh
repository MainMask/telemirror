#!/usr/bin/env bash
set -e

# Into this repo's .venv — the one the units run (/root/telemirror/.venv/bin/python),
# never the system Python or another venv left active.
if ! [ "${VIRTUAL_ENV:-}" -ef "$(dirname "$0")/.venv" ]; then
    echo "This repo's .venv isn't active: python3.13 -m venv .venv && source .venv/bin/activate, then bash install.sh" >&2
    exit 1
fi

# simple-lama-inpainting pins pillow<10 which doesn't build on Python 3.12+.
# Install it without its broken dependency metadata, then install everything else normally.
pip install "simple-lama-inpainting==0.1.2" --no-deps
pip install --upgrade pip
pip install -r requirements.txt

# torch (CPU build) — LaMa's runtime, for removing the source watermark from
# photos. Linux only: there are no wheels for Intel macOS / Python 3.13 there
# (without it photos are mirrored with the watermark left in place).
if [ "$(uname -s)" = "Linux" ]; then
    pip install "torch==2.5.1" --index-url https://download.pytorch.org/whl/cpu
fi
