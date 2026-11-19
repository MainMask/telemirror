"""The live mirror's sink of fan-out outcomes (``telemirror.outcomes``): the
weekly counters (``telemirror.stats``), the posts to copy again
(``telemirror.failed``) and one summary notice a minute about them."""

import logging
import time
from datetime import date
from typing import Dict, List, Optional

from telemirror.failed import FailedQueue
from telemirror.notify import BotNotifier, failed_buttons
from telemirror.outcomes import ALL_CHATS, FAILED, Outcomes
from telemirror.projects import load_chat_names
from telemirror.stats import Stats

logger = logging.getLogger("telemirror.sink")


def target_name(chat: int, names: Dict[int, str]) -> str:
    if chat == ALL_CHATS:
        return "все каналы"
    return names.get(chat) or str(chat)


class LiveSink:
    NOTICE_EVERY_SEC = 60
    STATS_EVERY_SEC = 600

    def __init__(self, key: str, notifier: Optional[BotNotifier], chat_mapping: dict) -> None:
        self.key = key
        self.failed = FailedQueue(key)
        self.stats = Stats(key, [(s, t) for s, targets in chat_mapping.items() for t in targets])
        self._targets = {s: list(targets) for s, targets in chat_mapping.items()}
        self._notifier = notifier
        self._unnoticed = 0  # posts failed since the last notice
        self._last: Optional[tuple] = None  # (link, Target) of the latest
        self._notice_at = float("-inf")
        self._stats_at = time.monotonic()

    def record(self, chat_id: int, ids: List[int], link: str, outcomes: Outcomes) -> None:
        for t in outcomes.targets:
            for target in self._counted_as(chat_id, t.chat):
                self.stats.add(chat_id, target, t.state)
        failed = outcomes.failed
        if failed:
            self.failed.upsert(chat_id, ids, link, failed)
            self._unnoticed += 1
            self._last = (link, failed[0])
        else:
            self.failed.remove(chat_id, ids[0])

    def retrying(self, entry: dict) -> None:
        """A post of the list is being copied again: off the list, and its
        last failure off the counters (of the day it was counted on) — the
        retry's own outcome is counted instead, so the weekly report counts
        the post once, as it ended up."""
        self.failed.drop(entry["id"])
        day = date.fromtimestamp(entry.get("at", 0))
        for t in entry.get("targets", []):
            for target in self._counted_as(entry["chat"], t.get("chat")):
                self.stats.remove(entry["chat"], target, FAILED, day)

    def _counted_as(self, source: int, chat: int) -> List[int]:
        """The directions a target's outcome counts for: its own; broken off
        before any target (ALL_CHATS) — every target of the source."""
        return self._targets.get(source, []) if chat == ALL_CHATS else [chat]

    def notice_text(self) -> str:
        assert self._last is not None
        link, target = self._last
        name = target_name(target.chat, load_chat_names(self.key))
        return (f"❗ Не скопировано постов: {self._unnoticed}. Последний: {link} → {name}: {target.reason}\n"
                "Повторить — кнопкой ниже или в «❗ Не скопировано» карточки проекта.")

    async def tick(self) -> None:
        """Every few seconds, from the mirror: the files, then the notice (if one is due)."""
        now = time.monotonic()
        self.failed.flush()
        if now - self._stats_at >= self.STATS_EVERY_SEC:
            self.stats.flush()
            self._stats_at = now
        if self._unnoticed and self._notifier is not None and now - self._notice_at >= self.NOTICE_EVERY_SEC:
            text = self.notice_text()
            self._unnoticed, self._notice_at = 0, now
            await self._notifier.send(text, failed_buttons(self.key))

    async def aclose(self) -> None:
        """The mirror stops: the files, then the notice still due — now, not a
        minute later (there's no later)."""
        self.close()
        if self._unnoticed and self._notifier is not None:
            text = self.notice_text()
            self._unnoticed = 0
            await self._notifier.send(text, failed_buttons(self.key))

    def close(self) -> None:
        """Write what's in memory."""
        for flush in (self.failed.flush, self.stats.flush):
            try:
                flush()
            except OSError as e:
                logger.error(f"Could not save the mirror's records: {type(e).__name__}: {e}")
