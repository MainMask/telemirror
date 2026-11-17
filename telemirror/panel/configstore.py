"""Read and safely rewrite a project's mirror YAML.

Every write goes: round-trip load (ruamel — comments, key order, ``!!set`` kept)
→ mutation → dump → semantic self-check against PyYAML (the loader config.py
uses) → validation by importing ``config`` in a subprocess against the
candidate, exactly the way the service would load it → ``.bak`` → atomic
replace, refused if the file changed on disk meanwhile (a manual edit).
"""

import asyncio
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

import yaml as pyyaml
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.util import load_yaml_guess_indent

from telemirror.panel import settings
from telemirror.panel.settings import Project

# `-100…` channel id with an optional `#topic`; ids are always -100-prefixed for
# channels/supergroups (the only peers a userbot can mirror between).
_CHAT_REF_RE = re.compile(r"^-100\d{5,}(?:#[1-9]\d{0,9})?$")


class ConfigError(Exception):
    """A refusal shown to the user: ``code`` picks the text (``texts.CONFIG_ERRORS``),
    ``detail`` is appended verbatim."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class Snapshot:
    text: str
    sha: str
    mtime: float
    data: Any  # ruamel CommentedMap


# ── parsing / input validation ──────────────────────────────────────────────


def normalize_chat_ref(raw: str) -> str:
    """User input → ``-100…`` or ``-100…#topic``; raises ConfigError."""
    value = raw.strip().replace("−", "-").replace("–", "-").replace(" ", "")
    if not _CHAT_REF_RE.fullmatch(value):
        raise ConfigError("bad_ref", raw.strip())
    return value


def parse_chat_refs(raw: str) -> list[str]:
    """Comma/space/newline-separated refs, de-duplicated, order kept."""
    out: list[str] = []
    for item in re.split(r"[,\s;]+", raw.strip()):
        if item:
            ref = normalize_chat_ref(item)
            if ref not in out:
                out.append(ref)
    if not out:
        raise ConfigError("bad_ref", raw.strip())
    return out


def chat_of(ref: str) -> int:
    return int(ref.split("#", 1)[0])


def _yaml_ref(ref: str) -> Any:
    # A bare id stays an int, like hand-written configs; a topic ref is a string.
    return int(ref) if "#" not in ref else ref


def ref_str(value: Any) -> str:
    return str(value).strip()


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


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_only_reason(project: Project) -> Optional[str]:
    """Why the panel must not write this project's file, or None.

    Values are keys of ``texts.READ_ONLY`` (kept UI-text-free here)."""
    if project.live and settings.YAML_CONFIG_ENV_SET:
        return "yaml_env"
    if not project.path.exists():
        return "env_mode" if project.live else "missing"
    return None


def load(project: Project) -> Snapshot:
    text = project.path.read_text(encoding="utf-8")
    data = _yaml_for(text).load(text)
    if data is None:
        data = CommentedMap()
    return Snapshot(text=text, sha=_sha(text), mtime=project.path.stat().st_mtime, data=data)


def directions(data: Any) -> list:
    return list(data.get("directions") or [])


def _plain(value: Any) -> Any:
    """ruamel nodes → plain JSON-able Python (sets sorted) for fingerprints."""
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (set, frozenset)):
        return sorted(str(v) for v in value)
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def fingerprint(direction: Any) -> str:
    """8-hex crc32 of a direction — callback data carries it so an action never
    lands on a different direction after the list shifted under a manual edit."""
    blob = json.dumps(_plain(direction), sort_keys=True, ensure_ascii=False)
    return f"{zlib.crc32(blob.encode('utf-8')):08x}"


def pairs(data: Any) -> set[tuple[str, str]]:
    """Every (source ref, target ref) pair the config declares."""
    out = set()
    for d in directions(data):
        for src in d.get("from") or []:
            for tgt in d.get("to") or []:
                out.add((ref_str(src), ref_str(tgt)))
    return out


# ── mutations (applied to ruamel data in place) ─────────────────────────────


def direction_at(data: Any, index: int, fp: str) -> Any:
    dirs = data.get("directions") or []
    if not 0 <= index < len(dirs) or fingerprint(dirs[index]) != fp:
        raise ConfigError("stale")
    return dirs[index]


def add_direction(
    data: Any, sources: list[str], targets: list[str], mode: str, full_history: bool
) -> None:
    if mode not in ("copy", "forward"):
        raise ConfigError("bad_mode", mode)
    for src in sources:
        for tgt in targets:
            if chat_of(src) == chat_of(tgt):
                raise ConfigError("self_loop", src)
    existing = pairs(data)
    clash = [(s, t) for s in sources for t in targets if (s, t) in existing]
    if clash:
        raise ConfigError("duplicate", ", ".join(f"{s} → {t}" for s, t in clash))

    def flow(items: list) -> CommentedSeq:
        seq = CommentedSeq(items)
        seq.fa.set_flow_style()
        return seq

    d = CommentedMap()
    d["from"] = flow([_yaml_ref(s) for s in sources])
    d["to"] = flow([_yaml_ref(t) for t in targets])
    if mode != data.get("mode", "copy"):
        d["mode"] = mode
    if full_history:
        d["past_mode"] = CommentedMap(full_history=True)
    if data.get("directions") is None:
        data["directions"] = CommentedSeq()
    data["directions"].append(d)


def delete_direction(data: Any, index: int, fp: str) -> None:
    direction_at(data, index, fp)
    del data["directions"][index]


def toggle_direction_flag(data: Any, index: int, fp: str, key: str) -> None:
    if key not in ("disable_edit", "disable_delete"):
        raise ValueError(key)
    d = direction_at(data, index, fp)
    d[key] = not bool(d.get(key, data.get(key, False)))


def toggle_global(data: Any, key: str) -> None:
    if key in ("disable_edit", "disable_delete"):
        data[key] = not bool(data.get(key, False))
    elif key == "mode":
        data[key] = "forward" if data.get(key, "copy") == "copy" else "copy"
    else:
        raise ValueError(key)


# ── writing ─────────────────────────────────────────────────────────────────


async def validate(project: Project, text: str) -> Optional[str]:
    """Load ``text`` through ``config.py`` in a subprocess, the way the
    project's service would. Returns the error's last line, or None if valid."""
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("YAML_CONFIG_ENV", "PANEL_BOT_TOKEN", "PYTHONPATH")
    }
    env["PYTHONPATH"] = str(settings.REPO_DIR)
    with tempfile.TemporaryDirectory(prefix="telemirror-panel-") as tmp:
        if project.loader == "file":
            # config.py reads ./.configs/mirror.config.yml relative to the cwd.
            (Path(tmp) / ".configs").mkdir()
            (Path(tmp) / ".configs" / "mirror.config.yml").write_text(text, encoding="utf-8")
        else:
            env["YAML_CONFIG_ENV"] = text
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", "import config",
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
            proc.kill()
            await proc.wait()
            return "timeout"
    if proc.returncode == 0:
        return None
    lines = [ln for ln in err.decode("utf-8", errors="replace").splitlines() if ln.strip()]
    return lines[-1] if lines else f"exit code {proc.returncode}"


Validator = Callable[[Project, str], Any]  # async (project, text) -> Optional[str]


class ConfigStore:
    def __init__(self, validator: Optional[Validator] = None) -> None:
        self._validate = validator or validate
        self._lock = asyncio.Lock()

    async def update(self, project: Project, mutate: Callable[[Any], None]) -> Snapshot:
        """Apply ``mutate`` to a fresh load of the file and write it back.
        Raises ConfigError on refusal; the file is then left untouched."""
        if read_only_reason(project):
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
            new_text = _dump(y, snap.data)
            error = await self._validate(project, new_text)
            if error:
                raise ConfigError("invalid", error)
            if _sha(project.path.read_text(encoding="utf-8")) != snap.sha:
                raise ConfigError("changed_on_disk")
            backup = project.path.with_suffix(project.path.suffix + ".bak")
            backup.write_text(snap.text, encoding="utf-8")
            tmp = project.path.with_name(f".{project.path.name}.panel-tmp")
            tmp.write_text(new_text, encoding="utf-8")
            os.replace(tmp, project.path)
            return load(project)
