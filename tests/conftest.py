"""Shared test helpers.

The filter pipeline is async but the project has no pytest-asyncio dependency,
so coroutines are driven synchronously with ``run()``.
"""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import pytest
from telethon.tl import types

from telemirror.messagefilters import strict_media_mode

REPO_ROOT = Path(__file__).resolve().parent.parent
ONE_DIRECTION = "directions:\n  - from: [-1001]\n    to: [-1002]\n"


def import_config(
    tmp_path: Path,
    code: str,
    mirror_config: str = ONE_DIRECTION,
    session: Optional[str] = None,
    cwd: Optional[Path] = None,
) -> subprocess.CompletedProcess:
    """Run ``code`` in a fresh interpreter (``telemirror.config`` resolves
    everything at import time) as a throwaway project with ``mirror_config``
    and ``session`` (default: the session's placeholder .jsession)."""
    projects = tmp_path / "projects"
    (projects / "p").mkdir(parents=True)
    (projects / "p" / "mirror.config.yml").write_text(mirror_config, encoding="utf-8")
    default_session = Path(os.environ["TELEMIRROR_PROJECTS_DIR"]) / "test.jsession"
    (projects / "p" / "project.yml").write_text(json.dumps({
        "name": "P", "session": session or str(default_session),
        "config": str(projects / "p" / "mirror.config.yml"), "port": 8123,
    }), encoding="utf-8")
    env = {**os.environ, "TELEMIRROR_PROJECTS_DIR": str(projects), "TELEMIRROR_PROJECT": "p",
           "PYTHONPATH": str(REPO_ROOT)}
    return subprocess.run([sys.executable, "-c", code], cwd=cwd or REPO_ROOT, env=env,
                          capture_output=True, text=True)


@pytest.fixture
def strict_media():
    """Run the test body with ``strict_media_mode`` on (past_mode semantics:
    filters re-raise MediaDownloadError instead of mirroring the original)."""
    token = strict_media_mode.set(True)
    try:
        yield
    finally:
        strict_media_mode.reset(token)


def run(coro):
    """Execute a coroutine (or awaitable) to completion and return its result."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        # cancel/drain leftover tasks so loop.close() stays quiet
        leftover = asyncio.all_tasks(loop)
        for task in leftover:
            task.cancel()
        if leftover:
            loop.run_until_complete(
                asyncio.gather(*leftover, return_exceptions=True)
            )
        loop.close()


def make_message(text="", entities=None, media=None, channel_id=1000):
    """Build a minimal ``types.Message`` usable as filter input.

    ``message.chat_id`` is derived from ``peer_id`` by Telethon.
    """
    return types.Message(
        id=1,
        peer_id=types.PeerChannel(channel_id),
        message=text,
        entities=entities,
        media=media,
    )


def entity_text(message, entity):
    """Return the substring an entity covers (UTF-16 offset/length aware)."""
    buf = message.message.encode("utf-16-le")
    return buf[entity.offset * 2 : (entity.offset + entity.length) * 2].decode("utf-16-le")
