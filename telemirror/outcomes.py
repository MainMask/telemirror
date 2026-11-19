"""What became of one new post (a message or an album) in each channel it was
for: sent, discarded by the filters, dropped as a repeat, or not sent (and
why). ``EventProcessor`` fills one per fan-out and hands it to its sink — the
live mirror's ``telemirror.sink.LiveSink``: the weekly counters and the list of
posts to copy again."""

import asyncio
from contextvars import ContextVar
from dataclasses import dataclass
from typing import List, Optional, Protocol

SENT, FILTERED, DUPLICATE, FAILED, PENDING = "sent", "filtered", "dup", "failed", "pending"
ALL_CHATS = 0  # a Target.chat: the post broke off before any channel was tried


@dataclass
class Target:
    chat: int
    topic: Optional[int]
    state: str = PENDING
    reason: str = ""


class Outcomes:
    """The fan-out walks its targets one by one: ``expect`` opens a target,
    the rest mark the one opened last."""

    def __init__(self) -> None:
        self.targets: List[Target] = []
        self.error: Optional[BaseException] = None  # what broke the fan-out off (logged, not raised)

    def expect(self, chat: int, topic: Optional[int]) -> None:
        self.targets.append(Target(chat, topic))

    def _mark(self, state: str) -> None:
        if self.targets:
            self.targets[-1].state = state

    def sent(self) -> None:
        self._mark(SENT)

    def filtered(self) -> None:
        self._mark(FILTERED)

    def duplicate(self) -> None:
        self._mark(DUPLICATE)

    def fail(self, reason: str) -> None:
        """The reason only: a target nothing marked sent ends up failed anyway."""
        if self.targets and self.targets[-1].state == PENDING:
            self.targets[-1].reason = reason

    def finish(self, error: Optional[BaseException] = None) -> None:
        """Every target still pending failed — ``error`` (or ``self.error``: the
        fan-out broke off) is the reason of those that have none; it broke off
        before any target: one for all the channels."""
        error = error or self.error
        if isinstance(error, asyncio.CancelledError):
            fallback = "зеркало остановилось"
        elif error is not None:
            fallback = f"{type(error).__name__}: {error}"
        else:
            fallback = "не отправлено"
        if error is not None and not self.targets:
            self.targets.append(Target(ALL_CHATS, None))
        for t in self.targets:
            if t.state == PENDING:
                t.state = FAILED
                t.reason = t.reason or fallback

    @property
    def failed(self) -> List[Target]:
        return [t for t in self.targets if t.state == FAILED]


class OutcomeSink(Protocol):
    def record(self, chat_id: int, ids: List[int], link: str, outcomes: Outcomes) -> None: ...


# The fan-out under way in this task: its send helpers mark its targets
# without carrying it through every call.
current: ContextVar[Optional[Outcomes]] = ContextVar("telemirror_outcomes", default=None)
