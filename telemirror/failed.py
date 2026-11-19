"""Posts the live mirror couldn't copy, and the panel's requests to copy them
again.

    projects/<key>/failed.json   written by the mirror only (``FailedQueue``)
    projects/<key>/requests/     the panel's requests: one empty file each —
                                 a post's id, ``all`` or ``clear``; the mirror
                                 handles and removes them

Each file has one writer, so the two processes never race on it."""

import hashlib
import json
import re
import time
from typing import Dict, List, Optional

from telemirror.outcomes import Target
from telemirror.projects import failed_path, requests_dir, write_json

MAX_ENTRIES = 300
MAX_AGE_SEC = 14 * 86400
ALL, CLEAR = "all", "clear"
_REQUEST_RE = re.compile(rf"[0-9a-f]{{8}}|{ALL}|{CLEAR}")


def entry_id(chat: int, first_id: int) -> str:
    """Short and stable: the panel's buttons carry it (≤64-byte callback data)."""
    return hashlib.sha1(f"{chat}:{first_id}".encode()).hexdigest()[:8]


def load(key: str) -> List[dict]:
    """The posts waiting, oldest first; [] when the file is missing or broken."""
    try:
        data = json.loads(failed_path(key).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [e for e in data if isinstance(e, dict) and "id" in e] if isinstance(data, list) else []


def request(key: str, what: str) -> None:
    """The panel: ask the mirror to copy a post again (its id), all of them, or
    to forget them (``clear``)."""
    if not _REQUEST_RE.fullmatch(what):
        raise ValueError(what)
    folder = requests_dir(key)
    folder.mkdir(exist_ok=True)
    (folder / what).touch()


def take_requests(key: str) -> List[str]:
    """The mirror: the requests waiting, in the order they were made (by name,
    🗑 clear then ♻️ all ran as all then clear: the posts just forgotten were
    copied again), each removed as it's taken. A request made again counts
    from its last time."""
    folder = requests_dir(key)
    if not folder.is_dir():
        return []
    out = []
    for path in sorted(folder.iterdir(), key=lambda p: (p.stat().st_mtime_ns, p.name)):
        if _REQUEST_RE.fullmatch(path.name):
            out.append(path.name)
        path.unlink(missing_ok=True)
    return out


class FailedQueue:
    """The mirror's side: kept in memory, written by ``flush`` when changed."""

    def __init__(self, key: str) -> None:
        self._key = key
        self._entries: Dict[str, dict] = {e["id"]: e for e in load(key)}
        self._dirty = False

    def upsert(self, chat: int, ids: List[int], link: str, targets: List[Target],
               now: Optional[float] = None) -> None:
        eid = entry_id(chat, ids[0])
        self._entries.pop(eid, None)  # re-added last: the newest at the end
        self._entries[eid] = {
            "id": eid, "at": int(now if now is not None else time.time()), "chat": chat, "ids": list(ids),
            "link": link, "targets": [{"chat": t.chat, "topic": t.topic, "reason": t.reason} for t in targets],
        }
        self._dirty = True

    def remove(self, chat: int, first_id: int) -> None:
        if self._entries.pop(entry_id(chat, first_id), None) is not None:
            self._dirty = True

    def drop(self, eid: str) -> None:
        if self._entries.pop(eid, None) is not None:
            self._dirty = True

    def clear(self) -> None:
        if self._entries:
            self._entries.clear()
            self._dirty = True

    def get(self, eid: str) -> Optional[dict]:
        return self._entries.get(eid)

    @property
    def entries(self) -> List[dict]:
        return list(self._entries.values())

    def flush(self, now: Optional[float] = None) -> None:
        cutoff = (now if now is not None else time.time()) - MAX_AGE_SEC
        for eid in [eid for eid, e in self._entries.items() if e.get("at", 0) < cutoff]:
            del self._entries[eid]
            self._dirty = True
        while len(self._entries) > MAX_ENTRIES:
            del self._entries[next(iter(self._entries))]
            self._dirty = True
        if self._dirty:
            write_json(failed_path(self._key), self.entries)
            self._dirty = False
