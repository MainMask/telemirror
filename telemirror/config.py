"""The settings a mirror process runs with: ``.env`` (account, database,
logging) and the mirror config YAML — the project's (``TELEMIRROR_PROJECT``,
set by ``telemirror@<key>.service``), else ``./.configs/mirror.config.yml``.
Everything is read at import time; a bad value fails the import.
"""

import math
import os
from typing import Dict, List, Literal, Optional, cast

import yaml
from decouple import AutoConfig

from telemirror.messagefilters import (
    CompositeMessageFilter,
    DocumentFilenameFilter,
    EmptyMessageFilter,
    ForwardFormatFilter,
    KeywordReplaceFilter,
    MessageFilter,
    RestrictSavingContentBypassFilter,
    StripFooterFilter,
    UrlMessageFilter,
    WatermarkRemovalFilter,
)
from telemirror import messagefilters
from telemirror.directions import DirectionConfig, PastModeConfig
from telemirror.misc.dsn import build_dsn
from telemirror.misc.jsession import load_jsession
from telemirror.projects import REPO_DIR, ProjectError, load_project

config = AutoConfig(search_path=str(REPO_DIR))


def _channel_id(value, name: str) -> Optional[int]:
    """Parse a channel-id env/YAML value; empty and ``"0"`` mean "unset"."""
    if value is None or str(value).strip() in ("", "0"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(
            f"{name}: expected an integer channel id, got {value!r}"
        ) from None


_VALID_MODES = {"copy", "forward"}


def _validate_mode(value: str, context: str) -> Literal["copy", "forward"]:
    """Fail fast on a bad `mode` instead of letting it silently mix the
    `== "forward"`/`== "copy"` branches downstream in mirroring.py."""
    if value not in _VALID_MODES:
        raise ValueError(
            f"{context}: mode must be 'copy' or 'forward', got {value!r}"
        )
    return cast(Literal["copy", "forward"], value)


def _validate_dedup_hours(value, context: str) -> float:
    """A negative ``dedup_hours`` is truthy: the check would be on with a
    cutoff in the future, and every fingerprint pruned each hour; ``.nan`` /
    ``.inf`` would break every check (``int()`` of them)."""
    try:
        if isinstance(value, bool):  # «true» isn't a number of hours (float() takes it as 1)
            raise ValueError
        hours = float(value or 0)
    except (TypeError, ValueError):  # «24h»: the same error, with the direction
        hours = math.nan
    if not math.isfinite(hours) or hours < 0:
        raise ValueError(f"{context}: dedup_hours must be 0 or more, got {value!r}")
    return hours


_CONTENT_MUTATING_FILTERS = (
    WatermarkRemovalFilter,
    DocumentFilenameFilter,
    RestrictSavingContentBypassFilter,
    UrlMessageFilter,
    KeywordReplaceFilter,
    ForwardFormatFilter,
    StripFooterFilter,
)


def _validate_forward_filters(filters: MessageFilter, mode: str, context: str) -> None:
    """Fail fast on `mode: forward` combined with a filter that mutates
    content: `_do_send` forwards the pristine original for `mode: forward`,
    so a content-mutating filter's output (re-uploaded media, rewritten
    text/entities) would be computed and then silently discarded."""
    if mode != "forward":
        return
    flat = filters.filters if isinstance(filters, CompositeMessageFilter) else [filters]
    offending = {type(f).__name__ for f in flat if isinstance(f, _CONTENT_MUTATING_FILTERS)}
    if offending:
        raise ValueError(
            f"{context}: mode 'forward' can't carry filters that mutate content "
            f"({', '.join(sorted(offending))}) — forward_messages() always sends "
            f"the pristine original, so their output would be silently discarded "
            f"and the work wasted. Use mode: copy, or drop these filters here."
        )


_MEDIA_CONSUMING_FILTERS = (RestrictSavingContentBypassFilter, DocumentFilenameFilter)


def _validate_watermark_filter_order(
    filters: MessageFilter, source: int, context: str
) -> None:
    """WatermarkRemovalFilter can't watermark media an earlier filter already
    re-uploaded (no raw bytes left) — see watermarkfilter.py's runtime WARNING.
    Fail fast at load time if the YAML lists a re-uploading filter
    (RestrictSavingContentBypassFilter, DocumentFilenameFilter) before any
    WatermarkRemovalFilter, including between two channel-scoped instances —
    but only when that WatermarkRemovalFilter actually processes `source`
    (its `channels` scoping, see watermarkfilter.py): a direction with
    multiple `from:` sources reuses the same filter list for each of them,
    and a channel-scoped instance that never touches `source` is not a real
    hazard for it, regardless of ordering."""
    flat = filters.filters if isinstance(filters, CompositeMessageFilter) else [filters]
    seen_consuming = None
    for f in flat:
        if isinstance(f, _MEDIA_CONSUMING_FILTERS) and seen_consuming is None:
            seen_consuming = type(f).__name__
        elif (
            isinstance(f, WatermarkRemovalFilter)
            and seen_consuming is not None
            and (f.channels is None or source in f.channels)
        ):
            raise ValueError(
                f"{context}: {seen_consuming} must not run before "
                f"WatermarkRemovalFilter — the watermark filter would silently "
                f"skip every image/video (no raw media left to process). "
                f"Reorder the filters."
            )


def _parse_chat_topic(value) -> tuple:
    """Split a ``chat_id`` or ``chat_id#topic_id`` value into ``(chat_id, topic_id)``.

    YAML may already hand back a plain ``int`` for a bare id.
    """
    if isinstance(value, str) and "#" in value:
        chat_id, topic_id = value.split("#")
        return int(chat_id), int(topic_id)
    return int(value), None


# (Optional) path to a `<phone>.jsession` file written by telemirror.login. When set,
# the session AND the client fingerprint (API_ID, API_HASH, API_DEVICE_MODEL,
# API_SYSTEM_VERSION, API_APP_VERSION, lang pack) all come from the file and
# the env values below are ignored. A relative path is taken from the repo
# root (where .env is found), not the current directory.
SESSION_FILE: Optional[str] = config("SESSION_FILE", default=None)

# (Optional) run as project <key> (projects/<key>/project.yml; systemd's
# telemirror@<key>.service sets it): the project's session, mirror config and
# health port replace SESSION_FILE, ./.configs/mirror.config.yml and PORT.
TELEMIRROR_PROJECT: Optional[str] = config("TELEMIRROR_PROJECT", default=None)
_project = load_project(TELEMIRROR_PROJECT) if TELEMIRROR_PROJECT else None
if _project:
    SESSION_FILE = _project.session

# Only set from a .jsession file; Telethon defaults otherwise.
API_LANG_PACK: Optional[str] = None
API_SYSTEM_LANG_CODE: Optional[str] = None

if SESSION_FILE:
    SESSION_FILE = str(REPO_DIR / SESSION_FILE)
    _jsession = load_jsession(SESSION_FILE)
    _app = _jsession["application"]
    API_ID: str = _app["api_id"]
    API_HASH: str = _app["api_hash"]
    API_SYSTEM_VERSION: Optional[str] = _app.get("sdk")
    API_DEVICE_MODEL: Optional[str] = _app.get("device_name")
    API_APP_VERSION: Optional[str] = _app.get("app_version")
    API_LANG_PACK = _app.get("lang_pack")
    API_SYSTEM_LANG_CODE = _app.get("system_lang_code")
    SESSION_STRING: str = _jsession["auth_key"]
else:
    # telegram app id
    API_ID = config("API_ID")
    # telegram app hash
    API_HASH = config("API_HASH")

    # The next optional parameters can be set to prevent bans/logouts
    # (Optional) System version info for telegram client. You can set it to `4.16.30-vxCUSTOM` or any other value if you believe it will help fix the bans. Default is `platform.uname().release`
    # See: https://github.com/LonamiWebs/Telethon/issues/4051
    API_SYSTEM_VERSION = config("API_SYSTEM_VERSION", default=None)
    # (Optional) Device model info for telegram client. Default is `platform.uname().machine`
    API_DEVICE_MODEL = config("API_DEVICE_MODEL", default=None)
    # (Optional) Application version info for telegram client. Default is `telethon.version.__version__`
    API_APP_VERSION = config("API_APP_VERSION", default=None)

    # auth session string: the `auth_key` of a .jsession file
    SESSION_STRING = config("SESSION_STRING")

USE_MEMORY_DB: bool = config("USE_MEMORY_DB", default=False, cast=bool)

# postgres: a connection string, or the credentials it is built from
DB_URL: Optional[str] = config("DATABASE_URL", default=None)
DB_NAME: Optional[str] = config("DB_NAME", default=None)
DB_USER: Optional[str] = config("DB_USER", default=None)
DB_PASS: Optional[str] = config("DB_PASS", default=None)
DB_HOST: Optional[str] = config("DB_HOST", default=None)

if not USE_MEMORY_DB and DB_URL is None and DB_HOST is None:
    raise Exception(
        "The database configuration is incorrect. "
        "Please provide valid DATABASE_URL (or DB_HOST, DB_NAME, DB_USER, DB_PASS) "
        "or set USE_MEMORY_DB to True to use in-memory database."
    )

if USE_MEMORY_DB:
    DB_URL = None
elif DB_URL is None:
    DB_URL = build_dsn(DB_USER, DB_PASS, cast(str, DB_HOST), DB_NAME)

LOG_LEVEL: str = config("LOG_LEVEL", default="INFO").upper()

# Application local host, defaults to 0.0.0.0
HOST: str = config("HOST", default="0.0.0.0")
# Application local port, defaults to 8000
PORT: int = _project.port if _project else config("PORT", default=8000, cast=int)

###############Channel mirroring config#################

YAML_CONFIG_FILE = str(_project.config_path if _project else REPO_DIR / ".configs" / "mirror.config.yml")
if not os.path.exists(YAML_CONFIG_FILE):
    if _project:
        raise ProjectError(f"project {_project.key!r}: mirror config {YAML_CONFIG_FILE} not found")
    raise FileNotFoundError(
        f"mirror config {YAML_CONFIG_FILE} not found — create it from "
        ".configs/mirror.config.yml-example or run as a project (TELEMIRROR_PROJECT)"
    )

# source and target chats mapping
CHAT_MAPPING: Dict[int, Dict[int, List[DirectionConfig]]] = {}

_bc = config("BROADCAST_CHANNEL", default=None)
BROADCAST_CHANNEL: Optional[int] = _channel_id(_bc, "BROADCAST_CHANNEL")

_bc_targets_str: Optional[str] = config("BROADCAST_TARGETS", default=None)
BROADCAST_TARGETS: Optional[List[str]] = (
    [s.strip() for s in _bc_targets_str.split(",") if s.strip()]
    if _bc_targets_str
    else None
)

_LIVE_SEND_DELAY: float = config("SEND_DELAY", default=0.5, cast=float)


with open(YAML_CONFIG_FILE, encoding="utf8") as _file:
    yaml_config = yaml.safe_load(_file) or {}
if not isinstance(yaml_config, dict) or not isinstance(yaml_config.get("directions"), list):
    raise ValueError(
        f"{YAML_CONFIG_FILE}: expected a mapping with a 'directions:' list "
        "(`directions: []` when there are none yet)"
    )

if "broadcast_channel" in yaml_config:
    BROADCAST_CHANNEL = _channel_id(
        yaml_config["broadcast_channel"], "broadcast_channel"
    )

if "broadcast_targets" in yaml_config:
    _raw_bt = yaml_config["broadcast_targets"]
    if not isinstance(_raw_bt, list):
        raise ValueError(
            f"broadcast_targets: expected a list, got {type(_raw_bt).__name__!r}"
        )
    BROADCAST_TARGETS = [str(t) for t in _raw_bt]


def build_filters(
    filter_config: Optional[dict], default: MessageFilter
) -> MessageFilter:
    if not filter_config:
        return default

    filters: List[MessageFilter] = []
    for entry in filter_config:
        if isinstance(entry, dict) and len(entry) != 1:
            # a mis-indented next filter lands in the same entry: don't drop it silently
            raise ValueError(
                f"filters: one filter per list item, got {', '.join(map(str, entry)) or 'none'} in one"
            )
        filter_name, filter_args = (
            list(entry.items())[0] if isinstance(entry, dict) else (entry, {})
        )
        filter_class = getattr(messagefilters, filter_name)
        filters.append(filter_class(**filter_args))

    return CompositeMessageFilter(filters) if (len(filters) > 1) else filters[0]


def build_past_mode(pm: Optional[dict]) -> Optional[PastModeConfig]:
    if not pm:
        return None
    return PastModeConfig(
        send_delay=pm.get("send_delay", 0.5),
        since_date=pm.get("since_date"),
        last_n=pm.get("last_n"),
        full_history=pm.get("full_history", False),
    )


default_filters = build_filters(
    yaml_config.get("filters", None), EmptyMessageFilter()
)

for direction in yaml_config["directions"]:
    sources: list = direction["from"]
    targets: list = direction["to"]
    # Built once per direction (not per source/target pair), so every pair
    # shares one filter instance — and its ReuploadCache — the same way
    # directions without their own `filters:` share `default_filters`.
    _direction_filters = build_filters(
        direction.get("filters", None), default_filters
    )

    for source in sources:
        source, source_topic_id = _parse_chat_topic(source)

        for target in targets:
            target, target_topic_id = _parse_chat_topic(target)

            _direction_mode = _validate_mode(
                direction.get("mode", yaml_config.get("mode", "copy")),
                f"{source}->{target}",
            )
            _validate_forward_filters(
                _direction_filters, _direction_mode, f"{source}->{target}"
            )
            _validate_watermark_filter_order(
                _direction_filters, source, f"{source}->{target}"
            )

            CHAT_MAPPING.setdefault(source, {}).setdefault(target, []).append(
                DirectionConfig(
                    disable_delete=direction.get(
                        "disable_delete", yaml_config.get("disable_delete", False)
                    ),
                    disable_edit=direction.get(
                        "disable_edit", yaml_config.get("disable_edit", False)
                    ),
                    filters=_direction_filters,
                    from_topic_id=source_topic_id,
                    to_topic_id=target_topic_id,
                    mode=_direction_mode,
                    past_mode=build_past_mode(direction.get("past_mode")),
                    send_delay=direction.get("send_delay", _LIVE_SEND_DELAY),
                    fallback_link_url=direction.get(
                        "fallback_link_url", yaml_config.get("fallback_link_url")
                    ),
                    dedup_hours=_validate_dedup_hours(
                        direction.get("dedup_hours", yaml_config.get("dedup_hours", 0)),
                        f"{source}->{target}",
                    ),
                )
            )

if BROADCAST_TARGETS is not None and not BROADCAST_CHANNEL:
    raise ValueError("BROADCAST_TARGETS requires BROADCAST_CHANNEL to be set")

if BROADCAST_CHANNEL:
    _bc_send_delay: float = config("BROADCAST_SEND_DELAY", default=0.5, cast=float)
    _all_broadcast_targets: Dict[int, set] = {}
    if BROADCAST_TARGETS is not None:
        for _item in BROADCAST_TARGETS:
            try:
                _ch, _tp = _parse_chat_topic(_item)
            except ValueError:
                raise ValueError(
                    f"BROADCAST_TARGETS: invalid entry {_item!r} — "
                    "expected 'channel_id' or 'channel_id#topic_id'"
                ) from None
            _all_broadcast_targets.setdefault(_ch, set()).add(_tp)
    else:
        for _src, _targets in CHAT_MAPPING.items():
            if _src == BROADCAST_CHANNEL:
                continue
            for _tgt_id, _cfgs in _targets.items():
                for _cfg in _cfgs:
                    _all_broadcast_targets.setdefault(_tgt_id, set()).add(_cfg.to_topic_id)

    _bc_filter = EmptyMessageFilter()
    for _tgt_id, _topic_ids in _all_broadcast_targets.items():
        _existing_topics = {
            _c.to_topic_id
            for _c in CHAT_MAPPING.get(BROADCAST_CHANNEL, {}).get(_tgt_id, [])
        }
        for _topic_id in _topic_ids:
            if _topic_id not in _existing_topics:
                CHAT_MAPPING.setdefault(BROADCAST_CHANNEL, {}).setdefault(
                    _tgt_id, []
                ).append(
                    DirectionConfig(
                        disable_delete=False,
                        disable_edit=False,
                        filters=_bc_filter,
                        to_topic_id=_topic_id,
                        mode="copy",
                        send_delay=_bc_send_delay,
                    )
                )
