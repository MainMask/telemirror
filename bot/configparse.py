"""The panel's input, checked before it reaches a config: channel refs, numbers,
dates, links, filter values — and ``ConfigError``, the refusal shown to the
user (``texts.CONFIG_ERRORS``)."""

import re
from datetime import datetime
from typing import Any

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


def parse_hours(raw: str) -> float:
    """Hours of 🧬 Без повторов: 0 (off) to 30 days."""
    try:
        value = float(raw.strip().replace(",", "."))
    except ValueError:
        raise ConfigError("bad_number", raw.strip()) from None
    if not 0 <= value <= 720:
        raise ConfigError("bad_number", raw.strip())
    return int(value) if value.is_integer() else value


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
