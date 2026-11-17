"""Read and safely rewrite a project's mirror YAML.

Every write goes: round-trip load (ruamel — comments, key order, ``!!set`` kept)
→ mutation → dump → semantic self-check against PyYAML (the loader config.py
uses) → validation by importing ``config`` in a subprocess against the
candidate, exactly the way the service would load it → ``.bak`` → atomic
replace, refused if the file changed on disk meanwhile (a manual edit).
"""

import asyncio
import copy
import difflib
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import zlib
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

import yaml as pyyaml
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq, CommentedSet
from ruamel.yaml.util import load_yaml_guess_indent

from telemirror.panel import settings
from telemirror.projects import Project

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


def yaml_ref(ref: str) -> Any:
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


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_only_reason(project: Project) -> Optional[str]:
    """Why the panel must not write this project's file, or None.

    Values are keys of ``texts.READ_ONLY`` (kept UI-text-free here)."""
    if not project.config_path.exists():
        return "missing"
    return None


def load(project: Project) -> Snapshot:
    path = project.config_path
    text = path.read_text(encoding="utf-8")
    data = _yaml_for(text).load(text)
    if data is None:
        data = CommentedMap()
    return Snapshot(text=text, sha=sha(text), mtime=path.stat().st_mtime, data=data)


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
    _check_pairs(data, sources, targets)
    d = CommentedMap()
    d["from"] = _flow([yaml_ref(s) for s in sources])
    d["to"] = _flow([yaml_ref(t) for t in targets])
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


def _flow(items: list) -> CommentedSeq:
    seq = CommentedSeq(items)
    seq.fa.set_flow_style()
    return seq


def _check_pairs(data: Any, sources: list[str], targets: list[str], skip: int = -1) -> None:
    """Refuse self-loops and pairs another direction (not ``skip``) already has."""
    for src in sources:
        for tgt in targets:
            if chat_of(src) == chat_of(tgt):
                raise ConfigError("self_loop", src)
    existing = set()
    for n, d in enumerate(directions(data)):
        if n != skip:
            existing |= {(ref_str(s), ref_str(t)) for s in d.get("from") or [] for t in d.get("to") or []}
    clash = [(s, t) for s in sources for t in targets if (s, t) in existing]
    if clash:
        raise ConfigError("duplicate", ", ".join(f"{s} → {t}" for s, t in clash))


def set_direction_refs(data: Any, index: int, fp: str, side: str, refs: list[str]) -> None:
    """Replace a direction's ``from`` or ``to`` list."""
    if side not in ("from", "to"):
        raise ValueError(side)
    d = direction_at(data, index, fp)
    sources = refs if side == "from" else [ref_str(r) for r in d.get("from") or []]
    targets = refs if side == "to" else [ref_str(r) for r in d.get("to") or []]
    _check_pairs(data, sources, targets, skip=index)
    d[side] = _flow([yaml_ref(r) for r in refs])


def toggle_direction_mode(data: Any, index: int, fp: str) -> None:
    d = direction_at(data, index, fp)
    current = d.get("mode", data.get("mode", "copy"))
    d["mode"] = "forward" if current == "copy" else "copy"


def set_direction_value(data: Any, index: int, fp: str, key: str, value: Any) -> None:
    """``send_delay`` (float), ``past_mode`` (mapping) or ``fallback_link_url``;
    None removes the key (the direction then inherits the default)."""
    if key not in ("send_delay", "past_mode", "fallback_link_url"):
        raise ValueError(key)
    d = direction_at(data, index, fp)
    if value is None:
        d.pop(key, None)
    elif key == "past_mode":
        # Keep a hand-set replay send_delay when switching the strategy.
        old = d.get("past_mode")
        pm = CommentedMap(value)
        if isinstance(old, dict) and "send_delay" in old:
            pm["send_delay"] = old["send_delay"]
        d[key] = pm
    else:
        d[key] = value


def replay_delays(data: Any) -> list:
    """``past_mode.send_delay`` of each direction with a history (None = default)."""
    return [d["past_mode"].get("send_delay") for d in directions(data)
            if isinstance(d.get("past_mode"), dict) and d["past_mode"]]


def set_direction_replay_delay(data: Any, index: int, fp: str, value: Optional[float]) -> None:
    """One direction's ``past_mode.send_delay``; None removes it (the default then)."""
    pm = direction_at(data, index, fp).get("past_mode")
    if not isinstance(pm, dict) or not pm:
        raise ConfigError("no_history")
    if value is None:
        pm.pop("send_delay", None)
    else:
        pm["send_delay"] = value


def set_replay_delay(data: Any, value: Optional[float]) -> int:
    """The replay's pause for every direction with a history; None removes it
    (config.py's default then). Returns how many directions it touched."""
    touched = 0
    for d in directions(data):
        pm = d.get("past_mode")
        if isinstance(pm, dict) and pm:
            if value is None:
                pm.pop("send_delay", None)
            else:
                pm["send_delay"] = value
            touched += 1
    if not touched:
        raise ConfigError("no_history")
    return touched


GLOBAL_VALUE_KEYS = ("tech_channel", "broadcast_channel", "broadcast_targets", "fallback_link_url")


def set_global_value(data: Any, key: str, value: Any) -> None:
    """None removes the key — config.py then falls back to the env var (for
    tech/broadcast) or to "unset"."""
    if key not in GLOBAL_VALUE_KEYS:
        raise ValueError(key)
    if value is None:
        data.pop(key, None)
    elif key == "broadcast_targets":
        data[key] = CommentedSeq(value)
    else:
        data[key] = value


# ── filters ─────────────────────────────────────────────────────────────────
# What the panel offers for each filter of telemirror/messagefilters: (arg, kind,
# default). Kinds: list-like — "set" (a !!set of strings), "list", "map"
# ("key => value"), "ids" (channel ids); scalars — "bool", "text", "number".
# An arg present in the file gets its kind from its value, so any hand-written
# arg of a known type is editable too; an arg of an unknown type is shown only.
LIST_KINDS = ("set", "list", "map", "ids")
SCALAR_KINDS = ("bool", "text", "number")
FILTER_ARGS: dict[str, tuple] = {
    "SkipWithKeywordsFilter": (("keywords", "set", None),),
    "AllowWithKeywordsFilter": (("keywords", "set", None),),
    "SkipWithUrlFilter": (("blacklist", "set", None),),
    "SkipUrlFilter": (("skip_mention", "bool", True),),
    "SkipAllFilter": (),
    "UrlMessageFilter": (("blacklist", "set", None), ("whitelist", "set", None), ("placeholder", "text", "***"),
                         ("filter_mention", "bool", False), ("filter_by_id_mention", "bool", False)),
    "KeywordReplaceFilter": (("keywords", "map", None),),
    "ForwardFormatFilter": (("format", "text", None),),
    "MappedNameForwardFormat": (("mapped", "map", None), ("format", "text", None)),
    "DocumentFilenameFilter": (("suffix", "text", ""), ("remove", "list", None)),
    # The rest of telemirror.watermark.processor.WatermarkConfig, with its defaults.
    "WatermarkRemovalFilter": (("remove_watermark", "bool", True), ("stamp_watermark", "bool", True),
                               ("template_path", "text", None), ("match_threshold", "number", 0.31),
                               ("channels", "ids", None),
                               ("scale_min", "number", 0.2), ("scale_max", "number", 1.0),
                               ("scale_steps", "number", 80), ("inpaint_dilate_px", "number", 6),
                               ("stamp_watermark_path", "text", None), ("stamp_opacity", "number", 0.55),
                               ("stamp_scale", "number", 0.35), ("stamp_video_max_duration_s", "number", 300.0),
                               ("stamp_video_preset", "text", "veryfast"), ("stamp_video_crf", "number", 18),
                               ("stamp_video_max_encode_s", "number", 180.0),
                               ("stamp_video_encode_realtime_ratio", "number", 0.73),
                               ("max_concurrent_video_encodes", "number", 1)),
    "RestrictSavingContentBypassFilter": (),
}
# Asked for when the filter is added: the filter can't be built without it.
REQUIRED_ARG = {"SkipWithKeywordsFilter": "keywords", "AllowWithKeywordsFilter": "keywords",
                "SkipWithUrlFilter": "blacklist", "KeywordReplaceFilter": "keywords"}
# Cheap filters that only drop messages: added before the transforming ones
# (the order rule of .configs/mirror.config.yml-example).
EARLY_FILTERS = frozenset({"SkipAllFilter", "SkipUrlFilter", "SkipWithUrlFilter", "SkipWithKeywordsFilter",
                           "AllowWithKeywordsFilter"})
# MappedNameForwardFormat needs both a mapping and a format to exist — hand-written only.
ADDABLE_FILTERS = tuple(n for n in FILTER_ARGS if n != "MappedNameForwardFormat")
_INT_KEY_MAPS = {("MappedNameForwardFormat", "mapped")}  # channel id → name
# A bool that may be a set of names instead (``filter_mention: [@a, @b]`` —
# only these): its first item replaces the bool, its last one going brings the default back.
BOOL_OR_SET = frozenset({("UrlMessageFilter", "filter_mention")})


@dataclass(frozen=True)
class FilterArg:
    key: str
    kind: str  # "" — a type the panel doesn't edit (shown only)
    value: Any  # None — not set in the file
    default: Any


def filters_of(data: Any, index: int) -> list:
    """Global filters (``index == -1``) or a direction's own ones."""
    if index < 0:
        return list(data.get("filters") or [])
    dirs = directions(data)
    if not 0 <= index < len(dirs):
        return []
    return list(dirs[index].get("filters") or [])


def filter_name(entry: Any) -> str:
    return str(next(iter(entry))) if isinstance(entry, dict) and entry else str(entry)


def _args_of(entry: Any) -> dict:
    args = next(iter(entry.values()), None) if isinstance(entry, dict) else None
    return args if isinstance(args, dict) else {}


def _kind_of(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "text"
    if isinstance(value, dict):
        return "map"
    if isinstance(value, AbstractSet):  # incl. ruamel's CommentedSet (a !!set)
        return "set"
    if isinstance(value, (list, tuple)):
        ints = value and all(isinstance(v, int) and not isinstance(v, bool) for v in value)
        return "ids" if ints else "list"
    return ""


def filter_args(entry: Any) -> list[FilterArg]:
    """The filter's args in the file (in its order), then the catalog's unset ones."""
    catalog = {key: (kind, default) for key, kind, default in FILTER_ARGS.get(filter_name(entry), ())}
    out = []
    for key, value in _args_of(entry).items():
        kind, default = catalog.get(str(key), ("", None))
        if value is not None and value != [] and value != {}:
            kind = _kind_of(value)
        out.append(FilterArg(str(key), kind, value, default))
    present = {a.key for a in out}
    out += [FilterArg(k, kind, None, default) for k, (kind, default) in catalog.items() if k not in present]
    return out


def editable_args(entry: Any) -> tuple[str, ...]:
    """The list-like args (edited item by item)."""
    return tuple(a.key for a in filter_args(entry) if a.kind in LIST_KINDS)


def int_keys(entry: Any, key: str) -> bool:
    return (filter_name(entry), key) in _INT_KEY_MAPS


def bool_or_set(entry: Any, key: str) -> bool:
    return (filter_name(entry), key) in BOOL_OR_SET


def filter_items(entry: Any, key: str) -> list[str]:
    """The arg's values as sorted strings (the order the panel numbers them in);
    a mapping's as ``key => value``."""
    value = _args_of(entry).get(key)
    if isinstance(value, dict):
        return sorted(f"{k} => {v}" for k, v in value.items())
    return sorted(str(v) for v in (value or []))


def _seq(data: Any, index: int) -> Any:
    if index < 0:
        return data.get("filters")
    dirs = data.get("directions") or []
    if not 0 <= index < len(dirs):
        raise ConfigError("stale")
    return dirs[index].get("filters")


def _owner(data: Any, index: int) -> Any:
    return data if index < 0 else data["directions"][index]


def _entry_at(data: Any, index: int, f: int, fp: str) -> Any:
    seq = _seq(data, index)
    if not seq or not 0 <= f < len(seq) or fingerprint(seq[f]) != fp:
        raise ConfigError("stale")
    return seq


def _writable_args(seq: Any, f: int) -> Any:
    """The entry's args mapping, turning ``- Name`` / ``- Name:`` into one."""
    name = filter_name(seq[f])
    if not isinstance(seq[f], dict):
        seq[f] = CommentedMap([(name, CommentedMap())])
    elif not isinstance(seq[f][name], dict):
        seq[f][name] = CommentedMap()
    return seq[f][name]


def _arg(seq: Any, f: int, key: str, kinds: tuple) -> FilterArg:
    arg = next((a for a in filter_args(seq[f]) if a.key == key), None)
    if arg is None or arg.kind not in kinds:
        raise ConfigError("bad_filter", f"{filter_name(seq[f])}.{key}")
    return arg


def _container(kind: str, items: list) -> Any:
    if kind == "set":
        return CommentedSet(items)
    if kind == "map":
        return CommentedMap(items)
    return _flow(list(items)) if kind == "ids" else CommentedSeq(items)


def add_filter(data: Any, index: int, dfp: str, name: str, items: Optional[list] = None) -> bool:
    """Add filter ``name`` (``items``: its REQUIRED_ARG's values). Early filters
    go after the leading run of early ones, the rest last. A direction without
    its own list gets a copy of the project's first — its own list replaces
    them, and adding one filter must not silently drop the rest. Returns
    whether that copy was made."""
    if name not in ADDABLE_FILTERS:
        raise ConfigError("bad_filter", name)
    copied = False
    if index >= 0:
        dirs = data.get("directions") or []
        if not 0 <= index < len(dirs) or fingerprint(dirs[index]) != dfp:
            raise ConfigError("stale")
    owner = _owner(data, index)
    if not owner.get("filters"):
        base = data.get("filters") if index >= 0 else None
        owner["filters"] = copy.deepcopy(base) if base else CommentedSeq()
        copied = bool(base)
    seq = owner["filters"]
    key = REQUIRED_ARG.get(name)
    if key:
        if not items:
            raise ConfigError("bad_item", name)
        kind = next(k for a, k, _ in FILTER_ARGS[name] if a == key)
        entry: Any = CommentedMap([(name, CommentedMap([(key, _container(kind, items))]))])
    else:
        entry = name
    if name in EARLY_FILTERS:
        pos = 0
        while pos < len(seq) and filter_name(seq[pos]) in EARLY_FILTERS:
            pos += 1
        seq.insert(pos, entry)
    else:
        seq.append(entry)
    return copied


def delete_filter(data: Any, index: int, f: int, fp: str) -> None:
    """The last of a list goes with the list: a direction then uses the project's."""
    seq = _entry_at(data, index, f, fp)
    del seq[f]
    if not seq:
        _owner(data, index).pop("filters", None)


def move_filter(data: Any, index: int, f: int, fp: str, step: int) -> None:
    seq = _entry_at(data, index, f, fp)
    j = f + step
    if step not in (-1, 1) or not 0 <= j < len(seq):
        raise ConfigError("stale")
    seq[f], seq[j] = seq[j], seq[f]


def set_filter_arg(data: Any, index: int, f: int, fp: str, key: str, value: Any) -> None:
    """A scalar arg; None removes it (the filter's default then)."""
    seq = _entry_at(data, index, f, fp)
    _arg(seq, f, key, SCALAR_KINDS)
    args = _writable_args(seq, f)
    if value is None:
        args.pop(key, None)
    else:
        args[key] = value


def add_filter_items(data: Any, index: int, f: int, fp: str, key: str, items: list) -> None:
    """``items``: strings; ints for "ids"; (key, value) pairs for "map"."""
    seq = _entry_at(data, index, f, fp)
    kind = _arg(seq, f, key, LIST_KINDS + (("bool",) if bool_or_set(seq[f], key) else ())).kind
    args = _writable_args(seq, f)
    value = args.get(key)
    if value is None or value == [] or value == {} or kind == "bool":
        args[key] = _container("set" if kind == "bool" else kind, items)
    elif kind == "map":
        for k, v in items:
            value[k] = v
    elif kind == "set":
        for item in items:
            value.add(item)
    else:
        value.extend(i for i in items if i not in value)


def remove_filter_item(data: Any, index: int, f: int, fp: str, key: str, n: int) -> str:
    """Remove the ``n``-th item (``filter_items`` order); returns it."""
    seq = _entry_at(data, index, f, fp)
    _arg(seq, f, key, LIST_KINDS)
    items = filter_items(seq[f], key)
    if not 0 <= n < len(items):
        raise ConfigError("stale")
    target = items[n]
    value = _args_of(seq[f])[key]
    if isinstance(value, dict):
        del value[next(k for k, v in value.items() if f"{k} => {v}" == target)]
        return target
    for v in list(value):
        if str(v) == target:
            if isinstance(value, list):
                value.remove(v)
            else:
                value.discard(v)
            break
    if not value and bool_or_set(seq[f], key):
        _args_of(seq[f]).pop(key)
    return target


# ── input parsing ───────────────────────────────────────────────────────────

CLEAR = "-"  # typed by the user to remove a value


def parse_channel_id(raw: str) -> int:
    ref = normalize_chat_ref(raw)
    if "#" in ref:
        raise ConfigError("bad_ref", raw.strip())
    return int(ref)


def parse_url(raw: str) -> str:
    value = raw.strip()
    if not re.fullmatch(r"https?://[^\s]+", value):
        raise ConfigError("bad_url", value)
    return value


def parse_delay(raw: str) -> float:
    try:
        value = float(raw.strip().replace(",", "."))
    except ValueError:
        raise ConfigError("bad_number", raw.strip()) from None
    if not 0 <= value <= 60:
        raise ConfigError("bad_number", raw.strip())
    return value


def parse_last_n(raw: str) -> int:
    value = raw.strip()
    if not value.isdigit() or not 1 <= int(value) <= 1_000_000:
        raise ConfigError("bad_number", value)
    return int(value)


def parse_since(raw: str) -> str:
    value = raw.strip()
    try:
        datetime.fromisoformat(value)
    except ValueError:
        raise ConfigError("bad_date", value) from None
    return value


def parse_filter_items(raw: str) -> list[str]:
    """One item per line (keywords may contain commas and spaces)."""
    items = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if len(line) > 200:
            raise ConfigError("bad_item", line[:50] + "…")
        if line not in items:
            items.append(line)
    if not items:
        raise ConfigError("bad_item", raw.strip())
    return items


def parse_items(kind: str, raw: str, int_keys: bool = False) -> list:
    """A list-like arg's new items: strings, channel ids ("ids") or
    ``key => value`` pairs ("map"; channel-id keys with ``int_keys``)."""
    if kind == "ids":
        ids = [parse_channel_id(x) for x in re.split(r"[,\s;]+", raw.strip()) if x]
        if not ids:
            raise ConfigError("bad_ref", raw.strip())
        return list(dict.fromkeys(ids))
    lines = parse_filter_items(raw)
    if kind != "map":
        return lines
    pairs = []
    for line in lines:
        key, sep, value = line.partition("=>")
        if not sep or not key.strip():
            raise ConfigError("bad_pair", line)
        pairs.append((parse_channel_id(key) if int_keys else key.strip(), value.strip()))
    return pairs


def parse_number(raw: str) -> Any:
    value = raw.strip().replace(",", ".")
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        raise ConfigError("bad_number", value) from None


def parse_text(raw: str) -> str:
    if len(raw) > 1000:
        raise ConfigError("bad_item", raw[:50] + "…")
    return raw


# ── writing ─────────────────────────────────────────────────────────────────


async def validate(project: Project, text: str) -> Optional[str]:
    """Load ``text`` through ``config.py`` in a subprocess, the way the
    project's service would (TELEMIRROR_PROJECT: its session, the candidate as
    its config). Returns the error's last line, or None if valid."""
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("YAML_CONFIG_ENV", "PANEL_BOT_TOKEN", "PYTHONPATH", "TELEMIRROR_PROJECT")
    }
    env["PYTHONPATH"] = str(settings.REPO_DIR)
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


MAX_UPLOAD_BYTES = 256 * 1024


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
            return await self._write(project, snap.sha, snap.text, _dump(y, snap.data))

    async def replace_text(self, project: Project, text: str, expected_sha: Optional[str] = None) -> Snapshot:
        """Replace the whole file (an uploaded config). The current content
        becomes the .bak. ``expected_sha``: refuse if the file changed since."""
        if read_only_reason(project):
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
    """Cheap shape check before the (slow) config.py validation."""
    if len(text.encode("utf-8")) > MAX_UPLOAD_BYTES:
        raise ConfigError("too_big", f"{MAX_UPLOAD_BYTES // 1024} KB")
    try:
        data = pyyaml.safe_load(text)
    except pyyaml.YAMLError as e:
        raise ConfigError("bad_yaml", str(e).splitlines()[0]) from None
    if not isinstance(data, dict) or not isinstance(data.get("directions"), list):
        raise ConfigError("bad_yaml", "no directions list")
