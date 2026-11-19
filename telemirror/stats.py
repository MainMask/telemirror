"""Per-day counters of the live mirror, by direction (source → target):
``projects/<key>/stats.json``, read by the weekly report (``telemirror.report``).

    {"pairs": [[source, target], …],          the directions configured now
     "days": {"2026-11-17": {"<source>><target>": [sent, filtered, dup, failed]}}}
                                              a day the mirror ran without a post: {}

The mirror keeps them in memory and writes them every few minutes and when it
stops (``flush``)."""

import json
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

from telemirror.outcomes import DUPLICATE, FAILED, FILTERED, SENT
from telemirror.projects import stats_path, write_json

FIELDS = (SENT, FILTERED, DUPLICATE, FAILED)
KEEP_DAYS = 35


def pair_key(source: int, target: int) -> str:
    return f"{source}>{target}"


def parse_pair(key: str) -> Tuple[int, int]:
    source, target = key.split(">")
    return int(source), int(target)


def load(key: str) -> dict:
    """{"pairs": [], "days": {}} when the file is missing or broken."""
    try:
        data = json.loads(stats_path(key).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    if not isinstance(data, dict):
        data = {}
    pairs = data.get("pairs") if isinstance(data.get("pairs"), list) else []
    days = data.get("days") if isinstance(data.get("days"), dict) else {}
    return {"pairs": pairs, "days": days}


def totals(data: dict, days: Iterable[date]) -> Dict[str, List[int]]:
    """{pair key: [sent, filtered, dup, failed]} summed over ``days``."""
    out: Dict[str, List[int]] = {}
    for day in days:
        for pair, counts in (data["days"].get(day.isoformat()) or {}).items():
            row = out.setdefault(pair, [0] * len(FIELDS))
            for n, value in enumerate(counts[: len(FIELDS)]):
                row[n] += int(value)
    return out


def quiet_days(data: dict, pairs: Iterable[Tuple[int, int]], today: Optional[date] = None) -> Optional[int]:
    """Days since any of ``pairs`` last counted a post — copied, filtered, a
    repeat or failed: 0 — today; KEEP_DAYS + 1 — none in the days kept; None —
    the mirror hasn't run with any of them yet."""
    keys = {pair_key(s, t) for s, t in pairs}
    if not keys & {pair_key(s, t) for s, t in data["pairs"]}:
        return None
    seen = [day for day, bucket in data["days"].items() if keys & set(bucket)]
    if not seen:
        return KEEP_DAYS + 1
    return ((today or date.today()) - date.fromisoformat(max(seen))).days


class Stats:
    def __init__(self, key: str, pairs: Iterable[Tuple[int, int]]) -> None:
        self._key = key
        self._data = load(key)
        self._data["pairs"] = sorted({(int(s), int(t)) for s, t in pairs})
        self._dirty = True  # the pairs, at least

    def add(self, source: int, target: int, state: str, day: Optional[date] = None) -> None:
        if state not in FIELDS:
            return
        bucket = self._data["days"].setdefault((day or date.today()).isoformat(), {})
        row = bucket.setdefault(pair_key(source, target), [0] * len(FIELDS))
        row[FIELDS.index(state)] += 1
        self._dirty = True

    def remove(self, source: int, target: int, state: str, day: date) -> None:
        """Take back one ``add`` (a counted failure whose post is copied
        again); nothing when that day or that pair isn't kept any more."""
        row = (self._data["days"].get(day.isoformat()) or {}).get(pair_key(source, target))
        if state in FIELDS and row and row[FIELDS.index(state)] > 0:
            row[FIELDS.index(state)] -= 1
            self._dirty = True

    def flush(self, today: Optional[date] = None) -> None:
        today = today or date.today()
        # A day the mirror ran is kept even without a post ({}): the report
        # tells a quiet week from a stopped mirror by it.
        if today.isoformat() not in self._data["days"]:
            self._data["days"][today.isoformat()] = {}
            self._dirty = True
        if not self._dirty:
            return
        oldest = (today - timedelta(days=KEEP_DAYS)).isoformat()
        self._data["days"] = {d: v for d, v in self._data["days"].items() if d >= oldest}
        write_json(stats_path(self._key), {"pairs": [list(p) for p in self._data["pairs"]],
                                           "days": self._data["days"]})
        self._dirty = False
