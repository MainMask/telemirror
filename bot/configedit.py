"""Changes to a project's mirror config, applied in place to its round-trip
(ruamel) data: directions, the project's defaults and channels, filters and
their args. Each takes the fingerprint of what the button showed, so a list
changed meanwhile (a manual edit) is refused instead of hitting another item."""

import copy
import json
import zlib
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import Any, Optional

from ruamel.yaml.comments import CommentedMap, CommentedSeq, CommentedSet

from bot.configparse import ConfigError, chat_of, ref_str, yaml_ref
from bot.filtercatalog import (
    _INT_KEY_MAPS,
    ADDABLE_FILTERS,
    AFTER_EARLY_FILTERS,
    BOOL_OR_SET,
    EARLY_FILTERS,
    FILTER_ARGS,
    LIST_KINDS,
    REQUIRED_ARG,
    SCALAR_KINDS,
)


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


def filter_fp(data: Any, index: int, entry: Any) -> str:
    """A filter entry's fingerprint (``FltCB.h``); a direction's (``index`` ≥ 0)
    includes the direction's channels — an old button can't reach an identical
    filter of the next direction after this one was deleted."""
    if index < 0:
        return fingerprint(entry)
    dirs = data.get("directions") or []
    owner = dirs[index] if 0 <= index < len(dirs) else {}
    return fingerprint([owner.get("from"), owner.get("to"), entry])


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


def set_replay_delay(data: Any, value: Optional[float]) -> int:
    """The replay's pause for every direction with a history; None removes it
    (telemirror.config's default then). Returns how many directions it touched."""
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


def set_history(data: Any, value: Optional[dict]) -> None:
    """What history every direction copies (``past_mode``: full_history /
    last_n / since_date); None — none. A replay pause already set is kept."""
    if not directions(data):
        raise ConfigError("no_directions")
    for d in directions(data):
        old = d.get("past_mode")
        if value is None:
            d.pop("past_mode", None)
            continue
        pm = CommentedMap(value)
        if isinstance(old, dict) and "send_delay" in old:
            pm["send_delay"] = old["send_delay"]
        d["past_mode"] = pm


def history_of(d: Any) -> Optional[dict]:
    """A direction's history choice without its pause — for comparing them."""
    pm = d.get("past_mode")
    if not isinstance(pm, dict):
        return None
    return {k: v for k, v in pm.items() if k != "send_delay"} or None


GLOBAL_VALUE_KEYS = ("broadcast_channel", "broadcast_targets", "fallback_link_url", "dedup_hours")


def set_global_value(data: Any, key: str, value: Any) -> None:
    """None removes the key — telemirror.config then falls back to the env var (for
    the broadcast) or to "unset"."""
    if key not in GLOBAL_VALUE_KEYS:
        raise ValueError(key)
    if value is None:
        data.pop(key, None)
    elif key == "broadcast_targets":
        data[key] = CommentedSeq(value)
    else:
        data[key] = value


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
    if not seq or not 0 <= f < len(seq) or filter_fp(data, index, seq[f]) != fp:
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
    go after the leading run of early ones, AFTER_EARLY_FILTERS right after it,
    the rest last. A direction without
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
    if name in EARLY_FILTERS or name in AFTER_EARLY_FILTERS:
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
