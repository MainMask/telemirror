"""Pytest session defaults so ``import config`` succeeds on a fresh checkout / CI.

``config.py`` reads required settings (``API_ID`` etc.) with no fallback, so any
test that imports it — directly or via ``telemirror`` / ``past_mode`` — needs them
present. These placeholders are applied ONLY when there is no local ``.env``; a
developer's real ``.env`` always wins (python-decouple checks ``os.environ`` before
the file, so we must not set anything when a real config exists).
"""

import os
from pathlib import Path

if not (Path(__file__).parent / ".env").exists():
    os.environ.setdefault("API_ID", "12345")
    os.environ.setdefault("API_HASH", "test")
    os.environ.setdefault("SESSION_STRING", "test")
    os.environ.setdefault("USE_MEMORY_DB", "true")
    # Overrides ./.configs/mirror.config.yml so tests don't depend on the live config.
    os.environ.setdefault(
        "YAML_CONFIG_ENV", "directions:\n  - from: [-1001]\n    to: [-1002]\n"
    )
