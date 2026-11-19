"""The per-direction settings the mirror runs with (built by ``telemirror.config``
from the project's YAML; kept apart so the core doesn't import the config)."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, Optional

from telemirror.messagefilters import MessageFilter


@dataclass(frozen=True)
class PastModeConfig:
    send_delay: float = 0.5
    since_date: Optional[datetime] = None  # accepts datetime/date/ISO-str, see __post_init__
    last_n: Optional[int] = None
    full_history: bool = False

    def __post_init__(self) -> None:
        # YAML auto-parses an unquoted `since_date` into a `datetime` (or a bare
        # date into `date`); normalize any of datetime/date/ISO-string to datetime.
        if self.since_date is not None and not isinstance(self.since_date, datetime):
            coerced = (
                datetime.combine(self.since_date, datetime.min.time())
                if isinstance(self.since_date, date)
                else datetime.fromisoformat(self.since_date)
            )
            object.__setattr__(self, "since_date", coerced)

        n = sum([self.since_date is not None, self.last_n is not None, self.full_history])
        if n != 1:
            raise ValueError(
                f"PastModeConfig: expected exactly one strategy (since_date/last_n/full_history), got {n}"
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
    fallback_link_url: Optional[str] = None
    # Don't send a post the target already got from another source post within
    # this many hours (telemirror.dedup); 0 — off.
    dedup_hours: float = 0

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
