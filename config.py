"""
Loads environment(.env)/config.yaml config
"""

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Literal, Optional

from decouple import AutoConfig, Csv, RepositoryEnv

from telemirror.messagefilters import (
    CompositeMessageFilter,
    EmptyMessageFilter,
    MessageFilter,
    UrlMessageFilter,
)


class RepositoryMultilineEnv(RepositoryEnv):
    """
    Retrieves option keys from .env files with fall back to os.environ.
    Multiline values are supported with '' or "" quoted strings.
    """

    def __init__(self, source, encoding=...):
        self.data = {}
        multiline_key = None
        multiline_quote_sign = None
        with open(source, encoding=encoding) as file_:
            for line in file_:
                if multiline_key:
                    k = multiline_key
                    v = line.rstrip()
                    if v and v[-1] == multiline_quote_sign:
                        v = v[:-1]
                        multiline_key = None
                        multiline_quote_sign = None

                    self.data[k] += f"\n{v}"
                    continue

                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip()
                if len(v) >= 2 and (
                    (v[0] == "'" and v[-1] == "'") or (v[0] == '"' and v[-1] == '"')
                ):
                    v = v[1:-1]
                elif v and (
                    (v[0] == "'" and (len(v) < 2 or v[-1] != "'"))
                    or (v[0] == '"' and (len(v) < 2 or v[-1] != '"'))
                ):
                    multiline_key = k
                    multiline_quote_sign = v[0]
                    v = v[1:]

                self.data[k] = v

        if multiline_key:
            raise ValueError(
                f"Unterminated multiline env string value for key = {multiline_key}, "
                f"expected {multiline_quote_sign} at end"
            )


class Config(AutoConfig):
    def __init__(self, search_path=None):
        super().__init__(search_path)
        self.SUPPORTED[".env"] = RepositoryMultilineEnv


config = Config()

# telegram app id
API_ID: str = config("API_ID")
# telegram app hash
API_HASH: str = config("API_HASH")

# The next optional parameters can be set to prevent bans/logouts
# (Optional) System version info for telegram client. You can set it to `4.16.30-vxCUSTOM` or any other value if you believe it will help fix the bans. Default is `platform.uname().release`
# See: https://github.com/LonamiWebs/Telethon/issues/4051
API_SYSTEM_VERSION: Optional[str] = config("API_SYSTEM_VERSION", default=None)
# (Optional) Device model info for telegram client. Default is `platform.uname().machine`
API_DEVICE_MODEL: Optional[str] = config("API_DEVICE_MODEL", default=None)
# (Optional) Application version info for telegram client. Default is `telethon.version.__version__`
API_APP_VERSION: Optional[str] = config("API_APP_VERSION", default=None)

# auth session string: can be obtain by run login.py
SESSION_STRING: str = config("SESSION_STRING")

USE_MEMORY_DB: bool = config("USE_MEMORY_DB", default=False, cast=bool)

# postgres credentials
# connection string
DB_URL: str = config("DATABASE_URL", default=None)
# or postgres credentials
DB_NAME: str = config("DB_NAME", default=None)
DB_USER: str = config("DB_USER", default=None)
DB_PASS: str = config("DB_PASS", default=None)
DB_HOST: str = config("DB_HOST", default=None)

if not USE_MEMORY_DB and DB_URL is None and DB_HOST is None:
    raise Exception(
        "The database configuration is incorrect. "
        "Please provide valid DATABASE_URL (or DB_HOST, DB_NAME, DB_USER, DB_PASS) "
        "or set USE_MEMORY_DB to True to use in-memory database."
    )

DB_PROTOCOL: str = "postgres"

# if connection string wasnt set then build it from credentials
if DB_URL is None:
    DB_URL = f"{DB_PROTOCOL}://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}"

LOG_LEVEL: str = config("LOG_LEVEL", default="INFO").upper()

# Application local host, defaults to 0.0.0.0
HOST: str = config("HOST", default="0.0.0.0")
# Application local port, defaults to 8000
PORT: int = config("PORT", default=8000, cast=int)

###############Channel mirroring config#################

YAML_CONFIG_ENV: Optional[str] = config("YAML_CONFIG_ENV", default=None)
YAML_CONFIG_FILE = "./.configs/mirror.config.yml"

# source and target chats mapping
CHAT_MAPPING: Dict[int, Dict[int, List["DirectionConfig"]]] = {}

_bc = config("BROADCAST_CHANNEL", default=None)
BROADCAST_CHANNEL: Optional[int] = int(_bc) if _bc else None

_bc_targets_str: Optional[str] = config("BROADCAST_TARGETS", default=None)
BROADCAST_TARGETS: Optional[List[str]] = (
    [s.strip() for s in _bc_targets_str.split(",") if s.strip()]
    if _bc_targets_str
    else None
)

_tc = config("TECH_CHANNEL", default=None)
TECH_CHANNEL: Optional[int] = int(_tc) if _tc else None

_LIVE_SEND_DELAY: float = config("SEND_DELAY", default=0.5, cast=float)


@dataclass(frozen=True)
class PastModeConfig:
    send_delay: float = 0.5
    since_date: Optional[datetime] = None
    last_n: Optional[int] = None
    full_history: bool = False

    def __post_init__(self) -> None:
        n = sum([self.since_date is not None, self.last_n is not None, self.full_history])
        if n != 1:
            raise ValueError(
                f"PastModeConfig: ожидается ровно одна стратегия (since_date/last_n/full_history), задано {n}"
            )


@dataclass(frozen=True)
class DirectionConfig:
    disable_delete: bool
    disable_edit: bool
    filters: MessageFilter
    from_topic_id: Optional[int] = None
    to_topic_id: Optional[int] = None
    mode: Literal["copy", "forward"] = "copy"
    past_mode: Optional[PastModeConfig] = None
    send_delay: float = 0.0

    def __repr__(self) -> str:
        return (
            f"mode: {self.mode}, "
            f"deleting: {not self.disable_delete}, "
            f"editing: {not self.disable_edit}, "
            f"{f'from_topic_id: {self.from_topic_id}, ' if self.from_topic_id else ''}"
            f"{f'to_topic_id: {self.to_topic_id}, ' if self.to_topic_id else ''}"
            f"{f'past_mode: {self.past_mode}, ' if self.past_mode else ''}"
            f"filters: {self.filters}"
        )


# Load mirror config from config.yml
# otherwise from .env or environment
if YAML_CONFIG_ENV or os.path.exists(YAML_CONFIG_FILE):
    from importlib import import_module
    from types import ModuleType

    import yaml

    filters_module: ModuleType = import_module("telemirror.messagefilters")

    yaml_config: dict = None

    if YAML_CONFIG_ENV:
        yaml_config = yaml.load(
            YAML_CONFIG_ENV.replace("\\n", "\n"), Loader=yaml.FullLoader
        )
    else:
        with open(YAML_CONFIG_FILE, encoding="utf8") as file:
            yaml_config = yaml.load(file, Loader=yaml.FullLoader)

    if "broadcast_channel" in yaml_config:
        BROADCAST_CHANNEL = int(yaml_config["broadcast_channel"])

    if "broadcast_targets" in yaml_config:
        _raw_bt = yaml_config["broadcast_targets"]
        if not isinstance(_raw_bt, list):
            raise ValueError(
                f"broadcast_targets: expected a list, got {type(_raw_bt).__name__!r}"
            )
        BROADCAST_TARGETS = [str(t) for t in _raw_bt]

    if "tech_channel" in yaml_config:
        TECH_CHANNEL = int(yaml_config["tech_channel"])

    def build_filters(
        filter_config: Optional[dict], default: MessageFilter
    ) -> MessageFilter:
        if not filter_config:
            return default

        filters: List[MessageFilter] = []
        for filter in filter_config:
            filter_name, filter_args = (
                list(filter.items())[0] if isinstance(filter, dict) else (filter, {})
            )
            filter_class = getattr(filters_module, filter_name)
            filters.append(filter_class(**filter_args))

        return CompositeMessageFilter(filters) if (len(filters) > 1) else filters[0]

    def build_past_mode(pm: Optional[dict]) -> Optional[PastModeConfig]:
        if not pm:
            return None
        return PastModeConfig(
            send_delay=pm.get("send_delay", 0.5),
            since_date=datetime.fromisoformat(pm["since_date"]) if "since_date" in pm else None,
            last_n=pm.get("last_n"),
            full_history=pm.get("full_history", False),
        )

    default_filters = build_filters(
        yaml_config.get("filters", None), EmptyMessageFilter()
    )

    for direction in yaml_config["directions"]:
        sources: list = direction["from"]
        targets: list = direction["to"]

        for source in sources:
            source_topic_id = None
            if isinstance(source, str):
                if "#" in source:
                    source, source_topic_id = map(int, source.split("#"))
                else:
                    source = int(source)

            for target in targets:
                target_topic_id = None
                if isinstance(target, str):
                    if "#" in target:
                        target, target_topic_id = map(int, target.split("#"))
                    else:
                        target = int(target)

                CHAT_MAPPING.setdefault(source, {}).setdefault(target, []).append(
                    DirectionConfig(
                        disable_delete=direction.get(
                            "disable_delete", yaml_config.get("disable_delete", False)
                        ),
                        disable_edit=direction.get(
                            "disable_edit", yaml_config.get("disable_edit", False)
                        ),
                        filters=build_filters(
                            direction.get("filters", None), default_filters
                        ),
                        from_topic_id=source_topic_id,
                        to_topic_id=target_topic_id,
                        mode=direction.get("mode", yaml_config.get("mode", "copy")),
                        past_mode=build_past_mode(direction.get("past_mode")),
                        send_delay=direction.get("send_delay", _LIVE_SEND_DELAY),
                    )
                )

else:
    # Mirror config thru environment vars
    from functools import partial

    def build_mapping_from_env(
        disable_edit: bool,
        disable_delete: bool,
        filters: MessageFilter,
        past_mode: Optional[PastModeConfig],
        env_str: str,
    ) -> Dict[int, Dict[int, List[DirectionConfig]]]:
        mapping: Dict[int, Dict[int, List[DirectionConfig]]] = {}

        if not env_str:
            return mapping

        import re

        matches = re.findall(
            r"\[?((?:-?\d+(?:#\d+)?,?)+):((?:-?\d+(?:#\d+)?,?)+)\]?",
            env_str,
            re.MULTILINE,
        )

        for sources, targets in matches:
            for source in sources.split(","):
                source_topic_id = None
                if "#" in source:
                    source, source_topic_id = map(int, source.split("#"))
                else:
                    source = int(source)

                for target in targets.split(","):
                    target_topic_id = None
                    if "#" in target:
                        target, target_topic_id = map(int, target.split("#"))
                    else:
                        target = int(target)

                    mapping.setdefault(source, {}).setdefault(target, []).append(
                        DirectionConfig(
                            disable_delete=disable_delete,
                            disable_edit=disable_edit,
                            filters=filters,
                            from_topic_id=source_topic_id,
                            to_topic_id=target_topic_id,
                            past_mode=past_mode,
                            send_delay=_LIVE_SEND_DELAY,
                        )
                    )

        return mapping

    # remove urls from messages
    REMOVE_URLS: bool = config("REMOVE_URLS", cast=bool, default=False)
    # remove urls whitelist
    REMOVE_URLS_WHITELIST: set = config(
        "REMOVE_URLS_WL", cast=Csv(post_process=set), default=""
    )
    # remove urls only this URLs
    REMOVE_URLS_LIST: set = config(
        "REMOVE_URLS_LIST", cast=Csv(post_process=set), default=""
    )

    DISABLE_EDIT: bool = config("DISABLE_EDIT", cast=bool, default=False)
    DISABLE_DELETE: bool = config("DISABLE_DELETE", cast=bool, default=False)

    if REMOVE_URLS:
        message_filter = UrlMessageFilter(
            blacklist=REMOVE_URLS_LIST, whitelist=REMOVE_URLS_WHITELIST
        )
    else:
        message_filter = EmptyMessageFilter()

    _PAST_MODE_STR: Optional[str] = config("PAST_MODE", default=None)

    def _parse_past_mode_env(value: Optional[str]) -> Optional[PastModeConfig]:
        if not value:
            return None
        v = value.strip()
        if v == "full_history":
            return PastModeConfig(full_history=True)
        if v.startswith("since_date="):
            return PastModeConfig(since_date=datetime.fromisoformat(v[len("since_date="):]))
        if v.startswith("last_n="):
            return PastModeConfig(last_n=int(v[len("last_n="):]))
        raise ValueError(f"PAST_MODE: неверный формат: {v!r}")

    _GLOBAL_PAST_MODE: Optional[PastModeConfig] = _parse_past_mode_env(_PAST_MODE_STR)

    cast_env_chat_mapping = partial(
        build_mapping_from_env,
        DISABLE_EDIT,
        DISABLE_DELETE,
        message_filter,
        _GLOBAL_PAST_MODE,
    )

    CHAT_MAPPING = config("CHAT_MAPPING", cast=cast_env_chat_mapping, default="")

    if not CHAT_MAPPING:
        raise Exception(
            "The chat mapping configuration is incorrect. "
            "Please provide valid non-empty CHAT_MAPPING environment variable."
        )

if BROADCAST_TARGETS is not None and not BROADCAST_CHANNEL:
    raise ValueError("BROADCAST_TARGETS requires BROADCAST_CHANNEL to be set")

if BROADCAST_CHANNEL:
    _bc_send_delay: float = config("BROADCAST_SEND_DELAY", default=0.5, cast=float)
    _all_broadcast_targets: Dict[int, set] = {}
    if BROADCAST_TARGETS is not None:
        for _item in BROADCAST_TARGETS:
            try:
                if "#" in _item:
                    _ch, _tp = _item.split("#", 1)
                    _all_broadcast_targets.setdefault(int(_ch), set()).add(int(_tp))
                else:
                    _all_broadcast_targets.setdefault(int(_item), set()).add(None)
            except ValueError:
                raise ValueError(
                    f"BROADCAST_TARGETS: invalid entry {_item!r} — "
                    "expected 'channel_id' or 'channel_id#topic_id'"
                )
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
