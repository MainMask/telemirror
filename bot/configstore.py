"""Read and safely rewrite a project's mirror YAML.

Every write goes: round-trip load (ruamel — comments, key order, ``!!set`` kept)
→ mutation (``configedit``) → dump → semantic self-check against PyYAML (the
loader telemirror.config uses) → validation by importing ``telemirror.config``
in a subprocess against the candidate, exactly the way the service would load
it → ``.bak`` → atomic replace, refused if the file changed on disk meanwhile
(a manual edit).
"""

import asyncio
import difflib
import hashlib
import io
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

import yaml as pyyaml
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.util import load_yaml_guess_indent

from bot import settings
from bot.configparse import ConfigError
from telemirror.projects import REPO_DIR, Project


@dataclass(frozen=True)
class Snapshot:
    text: str
    sha: str
    mtime: float
    data: Any  # ruamel CommentedMap


# ── reading ─────────────────────────────────────────────────────────────────


def _yaml_for(text: str) -> YAML:
    """A round-trip YAML instance matching the file's own indentation style
    (indentless PyYAML dumps vs. the example's indented lists)."""
    try:
        _, indent, block_seq_indent = load_yaml_guess_indent(text)
    except Exception:  # noqa: BLE001 - empty / odd file: fall back to defaults
        indent, block_seq_indent = 2, 0
    indent = indent or 2
    offset = block_seq_indent or 0
    y = YAML()
    y.preserve_quotes = True
    y.width = 4096  # never re-wrap long format strings
    y.indent(mapping=max(indent - offset, 2) if offset else indent, sequence=indent, offset=offset)
    return y


def _dump(y: YAML, data: Any) -> str:
    buf = io.StringIO()
    y.dump(data, buf)
    return buf.getvalue()


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load(project: Project) -> Snapshot:
    path = project.config_path
    text = path.read_text(encoding="utf-8")
    data = _yaml_for(text).load(text)
    if data is None:
        data = CommentedMap()
    return Snapshot(text=text, sha=sha(text), mtime=path.stat().st_mtime, data=data)


# ── writing ─────────────────────────────────────────────────────────────────


async def validate(project: Project, text: str) -> Optional[str]:
    """Load ``text`` through ``telemirror.config`` in a subprocess, the way the
    project's service would (TELEMIRROR_PROJECT: its session, the candidate as
    its config). Returns the error's last line, or None if valid."""
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("PANEL_BOT_TOKEN", "PYTHONPATH", "TELEMIRROR_PROJECT")
    }
    env["PYTHONPATH"] = str(REPO_DIR)
    with tempfile.TemporaryDirectory(prefix="telemirror-panel-") as tmp:
        candidate = Path(tmp) / "mirror.config.yml"
        candidate.write_text(text, encoding="utf-8")
        (Path(tmp) / project.key).mkdir()
        (Path(tmp) / project.key / "project.yml").write_text(pyyaml.safe_dump({
            "name": project.name, "session": str(project.session_path),
            "config": str(candidate), "port": project.port,
        }, allow_unicode=True), encoding="utf-8")
        env["TELEMIRROR_PROJECT"] = project.key
        env["TELEMIRROR_PROJECTS_DIR"] = tmp
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", "import telemirror.config",
            cwd=tmp,
            env=env,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, err = await asyncio.wait_for(
                proc.communicate(), settings.VALIDATE_TIMEOUT_SEC
            )
        except asyncio.TimeoutError:
            return "timeout"
        finally:
            if proc.returncode is None:  # timed out, or the panel is stopping
                proc.kill()
                await proc.wait()
    if proc.returncode == 0:
        return None
    lines = [ln for ln in err.decode("utf-8", errors="replace").splitlines() if ln.strip()]
    return lines[-1] if lines else f"exit code {proc.returncode}"


Validator = Callable[[Project, str], Any]  # async (project, text) -> Optional[str]


def backup_path(project: Project) -> Path:
    return project.config_path.with_suffix(project.config_path.suffix + ".bak")


@dataclass(frozen=True)
class BackupInfo:
    mtime: float
    directions: Optional[int]  # None: the .bak doesn't parse


def backup_info(project: Project) -> Optional[BackupInfo]:
    path = backup_path(project)
    if not path.exists():
        return None
    try:
        data = pyyaml.safe_load(path.read_text(encoding="utf-8")) or {}
        count: Optional[int] = len(data.get("directions") or [])
    except Exception:  # noqa: BLE001 - shown as "unknown", restore will validate
        count = None
    return BackupInfo(path.stat().st_mtime, count)




class ConfigStore:
    def __init__(self, validator: Optional[Validator] = None) -> None:
        self._validate = validator or validate
        self._lock = asyncio.Lock()

    async def _write(self, project: Project, expected_sha: str, old_text: str, new_text: str) -> Snapshot:
        """Validate ``new_text`` and swap it in; ``old_text`` becomes the .bak.
        Caller holds the lock."""
        error = await self._validate(project, new_text)
        if error:
            raise ConfigError("invalid", error)
        path = project.config_path
        if sha(path.read_text(encoding="utf-8")) != expected_sha:
            raise ConfigError("changed_on_disk")
        backup_path(project).write_text(old_text, encoding="utf-8")
        tmp = path.with_name(f".{path.name}.panel-tmp")
        tmp.write_text(new_text, encoding="utf-8")
        os.replace(tmp, path)
        return load(project)

    async def update(self, project: Project, mutate: Callable[[Any], object]) -> Snapshot:
        """Apply ``mutate`` to a fresh load of the file and write it back.
        Raises ConfigError on refusal; the file is then left untouched."""
        if not project.config_path.exists():
            raise ConfigError("read_only")
        async with self._lock:
            snap = load(project)
            y = _yaml_for(snap.text)
            # The round-trip dump of the *untouched* document must mean the
            # same thing to PyYAML; otherwise this file uses something ruamel
            # can't rewrite faithfully — refuse instead of corrupting it.
            if pyyaml.safe_load(_dump(y, snap.data)) != pyyaml.safe_load(snap.text):
                raise ConfigError("roundtrip")
            mutate(snap.data)
            return await self._write(project, snap.sha, snap.text, _dump(y, snap.data))

    async def replace_text(self, project: Project, text: str, expected_sha: Optional[str] = None) -> Snapshot:
        """Replace the whole file (an uploaded config). The current content
        becomes the .bak. ``expected_sha``: refuse if the file changed since."""
        if not project.config_path.exists():
            raise ConfigError("read_only")
        check_yaml(text)
        async with self._lock:
            current = project.config_path.read_text(encoding="utf-8")
            if expected_sha is not None and sha(current) != expected_sha:
                raise ConfigError("changed_on_disk")
            return await self._write(project, sha(current), current, text)

    async def restore_backup(self, project: Project) -> Snapshot:
        """Swap the file with its .bak (so a rollback is itself undoable)."""
        path = backup_path(project)
        if not path.exists():
            raise ConfigError("no_backup")
        return await self.replace_text(project, path.read_text(encoding="utf-8"))


def text_diff(old: str, new: str, limit: int = 1500) -> tuple[str, bool]:
    """Unified diff of two config texts (1 line of context), capped at
    ``limit`` chars. Returns (diff, truncated); an empty diff = identical."""
    lines = difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=1)
    body = "\n".join(ln for ln in lines if not ln.startswith(("---", "+++")))
    return (body[:limit], True) if len(body) > limit else (body, False)


def check_yaml(text: str) -> None:
    """Cheap shape check before the (slow) telemirror.config validation."""
    if len(text.encode("utf-8")) > settings.CONFIG_MAX_BYTES:
        raise ConfigError("too_big", f"{settings.CONFIG_MAX_BYTES // 1024} KB")
    try:
        data = pyyaml.safe_load(text)
    except pyyaml.YAMLError as e:
        raise ConfigError("bad_yaml", str(e).splitlines()[0]) from None
    if not isinstance(data, dict) or not isinstance(data.get("directions"), list):
        raise ConfigError("bad_yaml", "no directions list")
