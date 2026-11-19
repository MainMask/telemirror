"""Pytest session defaults: the tests run as a throwaway project, so
``telemirror.config`` imports on a fresh checkout / CI and never reads the
developer's real mirror config or database.

A minimal project (a placeholder ``.jsession`` and a one-direction config) is
written to a temp dir and selected through ``TELEMIRROR_PROJECTS_DIR`` /
``TELEMIRROR_PROJECT``; python-decouple reads ``os.environ`` before ``.env``,
so these win over a local ``.env``. Subprocess tests inherit them.
"""

import json
import os
import tempfile
from pathlib import Path

_root = Path(tempfile.mkdtemp(prefix="telemirror-tests-"))
(_root / "test").mkdir()
(_root / "test.jsession").write_text(
    json.dumps({"auth_key": "test", "application": {"api_id": 12345, "api_hash": "test"}}),
    encoding="utf-8",
)
(_root / "test" / "mirror.config.yml").write_text(
    "directions:\n  - from: [-1001]\n    to: [-1002]\n", encoding="utf-8"
)
(_root / "test" / "project.yml").write_text(
    json.dumps({
        "name": "Test", "session": str(_root / "test.jsession"),
        "config": str(_root / "test" / "mirror.config.yml"), "port": 8000,
    }),
    encoding="utf-8",
)
os.environ.update(
    TELEMIRROR_PROJECTS_DIR=str(_root), TELEMIRROR_PROJECT="test", USE_MEMORY_DB="true",
)
