"""History replay: copies the history of the directions that have
``past_mode:`` through the mirroring pipeline, resumable from a DB checkpoint.

    python -m telemirror.past        # telemirror-past@<key>.service, ⏪ Старые посты

Takes the project's session (the lock stops its live mirror's process from
sharing it; the panel pauses the mirror meanwhile).
"""

import asyncio
import logging
import sys
import time
from contextlib import nullcontext
from copy import deepcopy
from datetime import datetime
from functools import partial
from time import monotonic
from typing import Awaitable, Callable, Dict, List, Optional, Tuple, Union

from telethon import TelegramClient, errors, events, utils
from telethon.tl import types

from telemirror.account import open_account
from telemirror.config import CHAT_MAPPING, DB_URL, LOG_LEVEL, TELEMIRROR_PROJECT
from telemirror.directions import DirectionConfig
from telemirror.messagefilters import FilterAction, MediaDownloadError
from telemirror.mirroring import EventProcessor
from telemirror.misc.links import private_message_link
from telemirror.notify import BotNotifier
from telemirror.misc.log_setup import setup_stdout_logger
from telemirror.misc import sdnotify
from telemirror.misc.message_groups import iter_message_groups
from telemirror.misc.signals import cancel_on_sigterm
from telemirror.misc.telegram_client import cancel_and_await, connection_probe
from telemirror.storage import Database, MirrorMessage, open_database

_LOG_EVERY = 25  # log progress every N messages/albums
# On a dropped connection: bounded (the live mirror retries forever, a replay gives up)
_CONN_RETRIES = 20
_RETRY_DELAY = 3  # seconds between reconnect attempts

# MediaDownloadError = a transient Telegram file-serving failure that outlived
# download_media_with_retry's own retries. Wait and re-run from the checkpoint;
# after _MEDIA_RETRY_LIMIT consecutive attempts on the same message — skip past
# it, tell the panel's admins, and move on (don't crash-loop under systemd, don't
# hold the live mirror down for hours).
_MEDIA_RETRY_WAIT = 120  # seconds between retries
_MEDIA_RETRY_LIMIT = 5

# A FloodWait that keeps recurring at the very same checkpoint (Telegram never
# clears the throttle) would otherwise retry forever: the process stays alive
# but makes no progress, so systemd's Restart= never sees it as a crash and
# nothing alerts. Give up after this many consecutive same-checkpoint waits so
# it becomes a real, detectable, alertable process exit instead of a silent
# hang. Progress at a *different* checkpoint resets the count — normal
# flood-limiting churn across many directions must not trip this.
_FLOOD_RETRY_LIMIT = 20

# A drip's network blip or Telegram's own trouble (its bound lookup at the
# mirror's start, a pass) is waited out — else the pair stops till the next
# start (04:00); a longer outage is the watchdog's (it restarts the mirror).
_TRANSIENT = (OSError, errors.ServerError, errors.TimedOutError)  # OSError: ConnectionError, TimeoutError
_TRANSIENT_RETRY_WAIT = 60  # seconds
_TRANSIENT_RETRY_LIMIT = 5


def _configure_logging(log_level: str) -> logging.Logger:
    logger = setup_stdout_logger("past_mode", log_level)
    # Telethon's reconnection messages go through its own logger — give it the
    # same stdout format so they appear with timestamps alongside our progress logs.
    setup_stdout_logger("telethon", logging.WARNING)
    # The filters and media helpers log through `telemirror.*` module loggers
    # (download retries, skipped stamps) — same format and level as ours.
    setup_stdout_logger("telemirror", log_level)
    return logger


def _strategy_label(pm) -> str:
    if pm.since_date is not None:
        return f"since_date={pm.since_date.isoformat()}"
    if pm.last_n is not None:
        return f"last_n={pm.last_n}"
    return "full_history"


def _format_duration(seconds: float) -> str:
    if seconds >= 3600:
        return f"{seconds / 3600:.1f}h"
    if seconds >= 60:
        return f"{seconds / 60:.0f}min"
    return f"{seconds:.0f}s"


def _log_progress(
    logger: logging.Logger, prefix: str, processed: int, total: int, start_time: float
) -> None:
    elapsed = monotonic() - start_time
    if total > 0:
        pct = processed / total * 100.0
        eta = f", ETA {elapsed / processed * (total - processed):.0f}s" if processed >= 3 else ""
        logger.info(f"{prefix}: {processed}/{total} ({pct:.1f}%){eta}")
    else:
        logger.info(f"{prefix}: processed {processed}")


def _log_overall(
    logger: logging.Logger,
    pair_no: int,
    pair_count: int,
    done: int,
    total: int,
    run_start: float,
) -> None:
    """Cross-pair progress line spanning every channel pair."""
    elapsed = monotonic() - run_start
    if total > 0 and done > 0:
        pct = min(100.0, done / total * 100.0)
        eta = (
            f" • ETA ~{_format_duration(elapsed / done * (total - done))}"
            if done < total
            else ""
        )
        tail = f"overall ~{done}/{total} ({pct:.0f}%){eta}"
    else:
        tail = f"overall processed {done}"
    logger.info(
        f"[Progress] pair {pair_no}/{pair_count} • {tail} • elapsed {_format_duration(elapsed)}"
    )


async def _integrity_check(
    database: Database,
    source_id: int,
    target_id: int,
    logger: logging.Logger,
) -> tuple[Optional[int], int]:
    """Checks the checkpoint, returns (checkpoint, mirror count in DB up to it).

    The checkpoint is never rolled forward to the highest mirrored id: rows
    past it can come from the live mirror (telemirror.live) running between two
    past_mode runs, and jumping over them would silently skip every
    unreplayed message in between. Already-mirrored messages past the
    checkpoint are skipped per target by `EventProcessor`'s own dedup.
    """
    prefix = f"[PastMode] {source_id}→{target_id}"
    checkpoint = await database.get_past_mode_checkpoint(source_id, target_id)
    if checkpoint is None:
        return None, 0

    # Deduplicated by source message: overlapping DirectionConfigs (e.g. a
    # catch-all from_topic_id=None config plus a topic-scoped one) can mirror
    # the same source message to the same target twice, producing 2 rows —
    # a raw row count would overshoot the budget used for bounded last_n resume.
    # Counted by the DB: the pair's rows aren't loaded (tens of thousands for a
    # big channel, and a drip checks it inside the live mirror).
    # Only up to the checkpoint: past it are the live mirror's posts (beside a
    # drip, or between two runs) — not this history's, so not its budget.
    mirror_count = await database.count_mirrored(source_id, target_id, checkpoint)
    logger.info(f"{prefix}: checkpoint={checkpoint}, mirrors in DB up to it={mirror_count}")

    if mirror_count == 0:
        logger.warning(
            f"{prefix}: checkpoint={checkpoint} is set, but no mirrors were found "
            "(possibly every message was filtered out, or a DB issue)"
        )
        return checkpoint, 0

    return checkpoint, mirror_count


async def _remaining(
    client: TelegramClient,
    source_id: int,
    after_id: Optional[int],
    since_date,
    total: int,
    logger: logging.Logger,
    prefix: str,
    max_id: int = 0,
) -> int:
    """~How many messages a pass goes through, from ``after_id`` (a resume) or
    else from ``since_date``: the id span from there to the newest message
    (a drip's: to its bound ``max_id``).
    Ids of deleted and service messages count too, so it's capped by ``total``
    (the whole channel); ``total`` when it can't tell. Only the progress log
    uses it."""
    try:
        if after_id is None:
            before = await client.get_messages(source_id, limit=1, offset_date=since_date)
            after_id = before[0].id if before else 0
        if max_id:
            newest_id = max_id - 1
        else:
            newest = await client.get_messages(source_id, limit=1)
            newest_id = newest[0].id if newest else 0
        span = max(0, newest_id - after_id)
    except Exception as e:
        logger.warning(f"{prefix}: failed to estimate the messages left: {e}")
        return total
    return min(total, span) if total > 0 else span


async def _replay_direction(
    client: TelegramClient,
    database: Database,
    source_id: int,
    target_id: int,
    cfgs: List[DirectionConfig],
    logger: logging.Logger,
    total: Optional[int] = None,
    turns: Optional["_Turns"] = None,
    max_id: int = 0,
    live: Optional[EventProcessor] = None,
) -> int:
    """One pass over a channel's history for a (source, target) pair.

    Every topic-direction of the pair is handled in this single pass: the
    processor routes each message to whichever cfg's from_topic_id matches.
    `total` (source message count) is reused from `_run` when given.
    `turns`: a drip's, shared by the project's pairs — this pass works only
    on its turn (held from its start till a sent post's interval is out),
    but for a last_n's scan for where its posts begin (those, one at a time).
    `max_id`: a drip's bound (exclusive), fixed at the mirror's start.
    `live`: a drip's — the live mirror's processor, see `EventProcessor`.
    Returns the number of messages/albums processed — a drip's: sent.
    """
    pm = cfgs[0].past_mode
    assert pm is not None, "_replay_direction requires cfgs[0].past_mode to be set"
    prefix = f"[PastMode] {source_id}→{target_id}"
    pair = (source_id, target_id)
    if turns is not None:
        await turns.take(pair)

    labels = {_strategy_label(c.past_mode) for c in cfgs}
    if len(labels) > 1:
        logger.warning(
            f"{prefix}: the pair's topics have different past_mode strategies "
            f"({sorted(labels)}), using the first one ({_strategy_label(pm)})"
        )
    topics_note = "" if len(cfgs) == 1 else f", topics={len(cfgs)}"
    logger.info(f"{prefix}: starting (strategy={_strategy_label(pm)}{topics_note})")

    checkpoint, mirrors_done = await _integrity_check(database, source_id, target_id, logger)
    if checkpoint is not None:
        logger.info(f"{prefix}: resuming from message_id={checkpoint}")

    if total is None:
        try:
            total = (await client.get_messages(source_id, limit=0)).total
        except Exception as e:
            logger.warning(f"{prefix}: failed to get total: {e}")
            total = 0

    if pm.drip_interval is not None:
        # What's left of the interval since the pair's last sent post (an
        # earlier run's, kept in the DB) — waited out before this pass sends.
        last_sent, _ = await database.get_drip_state(source_id, target_id)
        await _wait_rest(last_sent, pm.drip_interval, logger, prefix)

    # last_n without a checkpoint: find where the last N begin (newest first,
    # ids only — a large last_n isn't held in memory), then stream from there.
    find_start = pm.last_n is not None and checkpoint is None
    # last_n *with* a checkpoint: resume with a raw-message budget instead of
    # a hard iter_messages(limit=...) cutoff — see the consumption loop below.
    bounded_resume = pm.last_n is not None and checkpoint is not None
    iter_kwargs: dict = {"reverse": True}
    if find_start:
        assert pm.last_n is not None  # implied by find_start
        first = last = None
        counted = 0
        if turns is not None:
            # Off the turn: a large last_n's scan is long (Telethon paces its
            # requests — hours for a million), the other pairs post meanwhile.
            turns.give(pair)
        # Bounded via limit=last_n plus an album margin rather than a hard
        # iter_messages(limit=last_n) cutoff: that could land mid-album (an
        # album is only known complete once iter_message_groups sees the
        # next non-matching message), silently dropping its older members.
        # +10 covers the worst case since Telegram caps albums at ~10 items.
        # iter_message_groups keeps each boundary album whole, so no manual
        # grouped_id tracking is needed here.
        async with turns.scan if turns is not None else nullcontext():
            async for group in iter_message_groups(
                client.iter_messages(source_id, limit=pm.last_n + 10, max_id=max_id)
            ):
                items = group if isinstance(group, list) else [group]
                last = last or max(m.id for m in items)
                first = min(m.id for m in items)
                counted += len(items)
                if counted >= pm.last_n:
                    break
        iter_total = counted
        # Exactly those: from the first of them (min_id is exclusive) up to
        # the newest of them (max_id too) — not what arrived meanwhile.
        iter_kwargs["min_id"] = (first or 1) - 1
        iter_kwargs["max_id"] = (last or 0) + 1
    else:
        if max_id:
            iter_kwargs["max_id"] = max_id
        if checkpoint is not None:
            iter_kwargs["min_id"] = checkpoint  # min_id is exclusive — resume from the next one
        elif pm.since_date is not None:
            iter_kwargs["offset_date"] = pm.since_date
        # full_history: reverse=True only
        if bounded_resume:
            assert pm.last_n is not None  # implied by bounded_resume
            iter_total = max(0, pm.last_n - mirrors_done)
            # Not bounded here via iter_messages(limit=...): a hard cutoff
            # could land mid-album (an album is only known complete once
            # iter_message_groups sees the next non-matching message),
            # splitting it across two replay passes. Bounded by `processed`
            # in the consumption loop below instead.
        elif checkpoint is not None or pm.since_date is not None:
            # not the whole channel: only what's after the checkpoint / the date
            iter_total = await _remaining(
                client, source_id, checkpoint, pm.since_date, total, logger, prefix, max_id
            )
        else:
            # a drip's: up to its bound, not the live mirror's posts since
            iter_total = min(total, max_id - 1) if max_id else total

    if iter_total > 0:
        if pm.drip_interval is not None:
            # the pairs take turns: this one's next post comes after each other pair's
            pairs = turns.left if turns is not None else 1
            eta_str = (
                f", at most ≈{_format_duration(iter_total * pm.drip_interval * pairs)} "
                f"(one post every {_format_duration(pm.drip_interval)}"
                + (f" from {pairs} pair(s) in turn" if pairs > 1 else "") + ", albums count once)"
            )
        elif pm.send_delay > 0:
            eta_str = (
                f", at least ≈{_format_duration(iter_total * pm.send_delay)} "
                "(send_delay only, download time not counted)"
            )
        else:
            eta_str = ""
        logger.info(f"{prefix}: ~{iter_total} message(s) to process{eta_str}")

    # Full CHAT_MAPPING is needed so _try_rewrite_tg_link can resolve cross-channel links.
    # Override only the current source to this single target pair to keep routing correct.
    processor = EventProcessor(
        chat_mapping={**CHAT_MAPPING, source_id: {target_id: cfgs}},
        database=database,
        client=client,
        logger=logger,
        strict_media_errors=True,  # exhausted transient download → retry, not degrade
        live=live,
    )

    processed = 0
    # Raw source-message count, as opposed to `processed` (one per group
    # regardless of album size): `iter_total` for a bounded resume is a
    # last_n budget in raw messages, so the stop check below must compare
    # against the same unit or it can overshoot by a whole album per group.
    messages_done = 0
    start_time = monotonic()

    def _log_step() -> None:
        # messages_done, not processed: iter_total counts messages, an album is several
        if processed == 1 or processed % _LOG_EVERY == 0:
            _log_progress(logger, prefix, messages_done, iter_total, start_time)

    async def mirrors_of(ids: List[int]) -> int:
        """How many mirrors of these source messages the target holds."""
        return sum(1 for m in await database.get_messages_batch(ids, source_id)
                   if m.mirror_channel == target_id)

    sent = 0
    # A drip's: when its next post may go, after one it sent — waited out
    # before the next one (`wait_turn`), not after the last: see the loop's end.
    owed: Optional[float] = None

    async def pace(ids: List[int], before: int, started: float) -> None:
        """A drip waits only after a post it actually sent (one already
        mirrored, filtered out or a service message costs no time), counted
        from when the post's sending started; otherwise ``send_delay``."""
        nonlocal sent, owed
        if pm.drip_interval is None:
            await asyncio.sleep(pm.send_delay)
        elif await mirrors_of(ids) > before:
            sent += 1
            # Kept in the DB: a restart (even a crash loop) waits out the rest
            # of the interval instead of sending the next post at once.
            await database.set_drip_sent(source_id, target_id, time.time())
            overall = f" · {turns.done}/{turns.pairs} pair(s) done" if turns is not None else ""
            logger.info(f"{prefix}: sent a post, gone through {messages_done}/{iter_total}, next in "
                        f"{_format_duration(pm.drip_interval)}{overall}")
            owed = started + pm.drip_interval

    async def wait_turn() -> bool:
        """A drip's next post: the rest of the interval after the one it sent,
        then the other pairs' posts. True — it waited."""
        nonlocal owed
        waited = False
        if owed is not None:
            await asyncio.sleep(max(0.0, owed - monotonic()))
            owed = None
            waited = True
            if turns is not None:
                turns.give(pair)  # the next pair's post now
        if turns is not None and await turns.take(pair):
            waited = True
        return waited

    async def process_single(msg) -> None:
        nonlocal processed, messages_done
        started = monotonic()
        before = await mirrors_of([msg.id]) if pm.drip_interval is not None else 0
        link = private_message_link(source_id, msg.id)
        await processor.new_message(source_id, msg, link)
        await database.set_past_mode_checkpoint(source_id, target_id, msg.id)
        processed += 1
        messages_done += 1
        _log_step()
        await pace([msg.id], before, started)

    async def process_album(album: List) -> None:
        nonlocal processed, messages_done
        started = monotonic()
        ids = [m.id for m in album]
        before = await mirrors_of(ids) if pm.drip_interval is not None else 0
        link = private_message_link(source_id, album[0].id)
        try:
            await processor.new_album(source_id, album, link)
        except MediaDownloadError as e:
            # The whole album failed together (no partial per-config send happens
            # before this propagates) — if retries are exhausted, give up on the
            # WHOLE album, not just the one item that failed, so earlier siblings
            # aren't silently excluded by a checkpoint landing between them.
            # e.message_id is overwritten for that checkpoint purpose only;
            # e.failed_message_id (set in MediaDownloadError.__init__)
            # still points at the item that actually failed to download, for
            # the skip notification below.
            e.message_id = album[-1].id
            raise
        await database.set_past_mode_checkpoint(source_id, target_id, album[-1].id)
        processed += 1
        messages_done += len(album)
        _log_step()
        await pace(ids, before, started)

    # Bounded resume: stop once iter_total raw messages have been processed,
    # checked before each group so a 0 total doesn't process anything. Checked
    # in raw-message units (messages_done), not groups, since a hard
    # iter_messages(limit=...) cutoff could otherwise land mid-album — the
    # budget can still overshoot by up to one album's size, but never
    # compounds across multiple albums.
    # iter_message_groups drops non-Message items (service messages): they produce
    # no mirror, so they no longer advance the checkpoint (same as _sync_broadcast_channel).
    fetched_again = True
    while fetched_again:
        fetched_again = False
        async for group in iter_message_groups(client.iter_messages(source_id, **iter_kwargs)):
            if bounded_resume and messages_done >= iter_total:
                break
            if pm.drip_interval is not None and await wait_turn():
                # Regression: fetched 100 at a time, a drip's posts went out as
                # they were hours before — an edit or a delete meanwhile found
                # no mirror for the live mirror to change. After a wait they're
                # fetched again, from the checkpoint: as they are now, the
                # deleted gone.
                resume_from = await database.get_past_mode_checkpoint(source_id, target_id)
                if resume_from is not None:
                    iter_kwargs["min_id"] = resume_from
                    iter_kwargs.pop("offset_date", None)
                fetched_again = True
                break
            if isinstance(group, list):
                await process_album(group)
            else:
                await process_single(group)

    if owed is not None and turns is not None and turns.left > 1:
        # The other pairs' next post only after this one's interval; with none
        # left, done now — not an interval later (a day, at a post a day).
        await asyncio.sleep(max(0.0, owed - monotonic()))

    if pm.drip_interval is not None:
        logger.info(f"{prefix}: done. Sent {sent} post(s), went through {processed}.")
        return sent
    logger.info(f"{prefix}: done. Processed {processed} message(s)/album(s).")
    return processed


async def _wait_rest(last_sent: Optional[float], interval: float, logger: logging.Logger, prefix: str) -> None:
    if last_sent is None:
        return
    # capped by the interval: a clock set back doesn't make it wait longer
    left = min(interval, last_sent + interval - time.time())
    if left > 0:
        logger.info(f"{prefix}: the last post went {_format_duration(interval - left)} ago, "
                    f"the next in {_format_duration(left)}")
        await asyncio.sleep(left)


async def _notify_skipped(source_id: int, message_id: int, unit: str, logger: logging.Logger) -> None:
    """Tell the panel's admins that past_mode gave up on one message (Telegram
    couldn't serve the file). Best effort — must not break the replay loop.
    ``unit``: whose journal its button opens — a drip's is the live mirror's."""
    notifier = BotNotifier.from_env(TELEMIRROR_PROJECT, unit)
    if notifier is None:
        return
    link = private_message_link(source_id, message_id)
    if not await notifier.send(
        f"⚠️ Копирование истории пропустило пост {link}: Telegram так и не отдал его файл. "
        "Перешлите его вручную, когда Telegram починится."
    ):
        logger.warning("could not tell the admins about the skipped post")


async def _replay_with_retry(
    client: TelegramClient,
    database: Database,
    source_id: int,
    target_id: int,
    cfgs: List[DirectionConfig],
    logger: logging.Logger,
    total: Optional[int] = None,
    turns: Optional["_Turns"] = None,
    max_id: int = 0,
    live: Optional[EventProcessor] = None,
) -> int:
    """Run `_replay_direction`, retrying on a >threshold FloodWait or an
    exhausted transient media download (`MediaDownloadError`). A drip's
    FloodWait is waited out on its turn (the whole account waits anyway); a
    file Telegram won't serve gives the turn to the other pairs meanwhile.

    Telethon auto-sleeps for waits ≤300s (flood_sleep_threshold); this loop
    handles the larger ones — raised either from iter_messages or from a send
    (mirroring re-raises both flood types). The checkpoint is saved as we go,
    so after sleeping we resume from where we left off.
    """
    media_failures = 0
    media_failure_checkpoint = object()  # sentinel: no stall seen yet
    flood_failures = 0
    flood_failure_checkpoint = object()  # sentinel: no stall seen yet
    transient_failures = 0
    transient_failure_checkpoint = object()  # sentinel: no stall seen yet
    while True:
        try:
            return await _replay_direction(
                client, database, source_id, target_id, cfgs, logger, total, turns=turns, max_id=max_id,
                live=live,
            )
        except (errors.FloodWaitError, errors.FloodPremiumWaitError) as e:
            checkpoint = await database.get_past_mode_checkpoint(source_id, target_id)
            if checkpoint != flood_failure_checkpoint:
                flood_failures = 0  # progressed since the last stall — fresh budget
                flood_failure_checkpoint = checkpoint
            flood_failures += 1
            if flood_failures > _FLOOD_RETRY_LIMIT:
                logger.error(
                    f"FloodWait recurring at the same checkpoint after "
                    f"{_FLOOD_RETRY_LIMIT} retries — giving up"
                    # a drip's: the live mirror goes on, the pair's tried again next start
                    + (" so systemd can restart and alert" if turns is None else "")
                )
                raise
            logger.warning(
                f"FloodWait {e.seconds}s, waiting and retrying "
                f"({flood_failures}/{_FLOOD_RETRY_LIMIT})..."
            )
            await asyncio.sleep(e.seconds)
        except _TRANSIENT as e:
            if turns is None:
                raise  # the unit: systemd restarts it from the checkpoint
            checkpoint = await database.get_past_mode_checkpoint(source_id, target_id)
            if checkpoint != transient_failure_checkpoint:
                transient_failures = 0  # progressed since the last stall — fresh budget
                transient_failure_checkpoint = checkpoint
            transient_failures += 1
            if transient_failures > _TRANSIENT_RETRY_LIMIT:
                raise
            logger.warning(
                f"{type(e).__name__}: {e} — waiting {_TRANSIENT_RETRY_WAIT}s and retrying from the "
                f"checkpoint ({transient_failures}/{_TRANSIENT_RETRY_LIMIT})"
            )
            turns.give((source_id, target_id))  # the other pairs' posts meanwhile, if they can
            await asyncio.sleep(_TRANSIENT_RETRY_WAIT)
        except MediaDownloadError as e:
            checkpoint = await database.get_past_mode_checkpoint(source_id, target_id)
            if checkpoint != media_failure_checkpoint:
                media_failures = 0  # progressed since the last stall — fresh budget
                media_failure_checkpoint = checkpoint
            media_failures += 1
            if media_failures > _MEDIA_RETRY_LIMIT:
                if e.message_id is None:
                    raise  # can't skip what we can't name
                # failed_message_id is the message_id as raised
                # (see MediaDownloadError.__init__), so this is never None here.
                assert e.failed_message_id is not None
                logger.error(
                    f"{e} — {_MEDIA_RETRY_LIMIT} retries didn't help, "
                    f"skipping message {e.failed_message_id} and moving on"
                )
                assert cfgs[0].past_mode is not None
                unit = "past" if cfgs[0].past_mode.drip_interval is None else "live"
                await _notify_skipped(source_id, e.failed_message_id, unit, logger)
                await database.set_past_mode_checkpoint(source_id, target_id, e.message_id)
                media_failures = 0
                media_failure_checkpoint = e.message_id
                continue
            logger.warning(
                f"{e} — waiting {_MEDIA_RETRY_WAIT}s and retrying from the checkpoint "
                f"({media_failures}/{_MEDIA_RETRY_LIMIT})"
            )
            if turns is not None:
                turns.give((source_id, target_id))
            await asyncio.sleep(_MEDIA_RETRY_WAIT)


async def _edit_links_pass(
    client: TelegramClient,
    database: Database,
    pairs: Dict[Tuple[int, int], List[DirectionConfig]],
    logger: logging.Logger,
    beside_live: bool = False,
) -> bool:
    """Second pass: fixes cross-channel links in already-sent messages.
    False: Telegram didn't give some messages, or the network failed an edit
    (left unfixed — worth another pass; a mirror it won't let edit isn't:
    that one wouldn't change). ``beside_live``: a drip's, the live mirror
    running too."""
    complete = True
    for (source_id, target_id), cfgs in pairs.items():
        # Work here is pair-wide (binding_id is keyed by channel pair); the
        # pair's first copy-mode topic drives send_delay. Each mirror's own
        # filters/fallback_link_url come from the direction that produced it
        # (matched by its topics, see below).
        copy_cfgs = [c for c in cfgs if c.mode == "copy"]
        if not copy_cfgs:
            continue
        cfg = copy_cfgs[0]
        assert cfg.past_mode is not None, "pairs values are pre-filtered to past_mode-configured cfgs"

        prefix = f"[EditPass] {source_id}→{target_id}"
        mirrors = await database.get_messages_for_channel_pair(source_id, target_id)
        if not mirrors:
            continue

        processor = EventProcessor(
            chat_mapping={**CHAT_MAPPING, source_id: {target_id: [cfg]}},
            database=database,
            client=client,
            logger=logger,
        )

        # A source message can hold more than one mirror in this pair when
        # it's reached by more than one topic-scoped config — keep every one
        # of them, not just the last seen, or only one topic's copy would
        # ever get its link fixed. Each mirror's own `mirror_topic_id` is
        # used below to resolve *its* referenced-link target correctly.
        mirror_map: Dict[int, List[MirrorMessage]] = {}
        for m in mirrors:
            mirror_map.setdefault(m.original_id, []).append(m)
        _ids = list(mirror_map.keys())
        _BATCH = 100
        edited = 0
        # Stream the source messages batch by batch — for a full_history replay
        # `mirrors` can be tens of thousands, and accumulating every Message
        # object here just to iterate it once was a needless memory spike.
        for _i in range(0, len(_ids), _BATCH):
            try:
                src_batch = await client.get_messages(
                    source_id, ids=_ids[_i : _i + _BATCH]
                )
            except Exception as e:
                logger.warning(f"{prefix}: failed to fetch message batch: {e}")
                complete = False
                break

            # (mirror, text, entities, the source's edit_date) the mirror should now carry.
            planned: List[Tuple[MirrorMessage, str, list, Optional[datetime]]] = []
            for src_msg in src_batch:
                if not src_msg or not src_msg.entities:
                    continue
                if not any(
                    isinstance(e, (types.MessageEntityTextUrl, types.MessageEntityUrl))
                    for e in src_msg.entities
                ):
                    continue

                # Rewritten per-mirror (not once per src_msg): different
                # topics of the same channel can hold different mirrors of a
                # referenced message, so each mirror's own `mirror_topic_id`
                # must drive its own link resolution. The per-URL DB lookup
                # itself is topic-independent (see `_rewrite_links`'s own
                # docstring), so one `link_cache` is shared across every
                # mirror of this src_msg — same reasoning as `new_message`/
                # `new_album`'s per-event cache in mirroring.py.
                link_cache: dict = {}
                # Baseline for the "does this pass touch any link at all"
                # check below — identical for every mirror of this src_msg.
                entities_before = deepcopy(src_msg.entities)
                text_before = src_msg.message
                for mirror in mirror_map[src_msg.id]:
                    mirror_cfg = EventProcessor._config_for_topic(
                        copy_cfgs, mirror.source_topic_id, mirror.mirror_topic_id,
                        lambda c: False,
                    ) or cfg
                    msg_copy = processor.copy_message(src_msg)
                    await processor._rewrite_links(
                        msg_copy, source_id, target_id, mirror_cfg.fallback_link_url,
                        link_cache=link_cache, to_topic_id=mirror.mirror_topic_id,
                    )

                    text_changed = msg_copy.message != text_before
                    url_changed = any(
                        getattr(a, "url", None) != getattr(b, "url", None)
                        for a, b in zip(
                            msg_copy.entities or [], entities_before or [], strict=False
                        )
                    )
                    if not text_changed and not url_changed:
                        continue  # no link this pass rewrites

                    # Same order as new_message: rewrite links, then the
                    # direction's filters — so text filters (KeywordReplace,
                    # UrlMessage, ForwardFormat) aren't reverted by this edit.
                    # Media is dropped first: only text is edited here, and
                    # every re-uploading filter is a no-op without media.
                    msg_copy.media = None
                    try:
                        action, filtered = await mirror_cfg.filters.process(
                            msg_copy, events.NewMessage.Event
                        )
                    except Exception as e:
                        logger.warning(
                            f"{prefix}: filter chain failed for {mirror.mirror_id}: "
                            f"{type(e).__name__}: {e}"
                        )
                        continue
                    if action is FilterAction.DISCARD:
                        continue
                    # A single message in → a single message back (see
                    # EventProcessor.edit_message).
                    assert not isinstance(filtered, list)
                    planned.append(
                        (mirror, filtered.message or "", filtered.entities or [], src_msg.edit_date)
                    )

            if not planned:
                continue

            # Compare with what each mirror carries now: one that already has
            # the rewritten link (resolved at send time, or fixed by an
            # earlier run) needs no edit — it would only draw a
            # MessageNotModifiedError and burn an edit request.
            try:
                current_batch = await client.get_messages(
                    target_id, ids=[m.mirror_id for m, _t, _e, _d in planned]
                )
            except Exception as e:
                logger.warning(f"{prefix}: failed to fetch mirror batch: {e}")
                complete = False
                continue
            current = {m.id: m for m in current_batch if m}

            for mirror, text, entities, edit_date in planned:
                cur = current.get(mirror.mirror_id)
                if cur is None:
                    continue  # mirror deleted
                if (cur.message or "") == text and list(cur.entities or []) == entities:
                    continue
                if (
                    cur.media is not None
                    and not isinstance(cur.media, types.MessageMediaWebPage)
                    and not cur.message
                    and len(utils.add_surrogate(text)) > 1024
                ):
                    # Sent via the caption-split fallback (empty caption + an
                    # untracked text reply): the caption can't hold this text.
                    # A long caption sent whole (Premium account) is edited.
                    continue

                # Only beside the live mirror can a post be edited meanwhile
                # (the standalone unit stops it): a request per edit else.
                edited_since = (partial(_edited_since, client, source_id, mirror.original_id, edit_date)
                                if beside_live else None)
                try:
                    if edited_since is not None and await edited_since():
                        continue
                    await _edit_waiting_out_flood(
                        client, logger, prefix, edited_since,
                        entity=target_id,
                        message=mirror.mirror_id,
                        text=text,
                        formatting_entities=entities,
                        # Keep the mirror's own preview state: Telethon's
                        # default (True) would add one to a mirror without it.
                        link_preview=isinstance(cur.media, types.MessageMediaWebPage),
                    )
                    edited += 1
                    logger.info(f"{prefix}: fixed link in {mirror.original_id}→{mirror.mirror_id}")
                    if cfg.past_mode.send_delay:
                        await asyncio.sleep(cfg.past_mode.send_delay)
                except Exception as e:
                    logger.warning(
                        f"{prefix}: error editing {mirror.mirror_id}: "
                        f"{type(e).__name__}: {e}"
                    )
                    if isinstance(e, _TRANSIENT + (errors.FloodWaitError, errors.FloodPremiumWaitError)):
                        complete = False  # the network or Telegram, not a refusal: worth another pass

        if edited:
            logger.info(f"{prefix}: fixed {edited} message(s)")
    return complete


async def _edited_since(client: TelegramClient, source_id: int, message_id: int,
                        edit_date: Optional[datetime]) -> bool:
    """The link pass waits between edits (a FloodWait too): a source post
    edited since its batch was read got that edit from the live mirror beside
    a drip, links fixed — not undone with the old text."""
    fresh = (await client.get_messages(source_id, ids=[message_id]))[0]
    return fresh is None or fresh.edit_date != edit_date


async def _edit_waiting_out_flood(client: TelegramClient, logger: logging.Logger, prefix: str,
                                  edited_since: Optional[Callable[[], Awaitable[bool]]], **kwargs) -> None:
    """``client.edit_message``; a FloodWait over Telethon's own threshold (it
    sleeps through the shorter ones) is waited out once — this pass has no
    retry of its own, and skipping would leave the link unfixed for good —
    unless the source post was edited meanwhile (``edited_since``; None —
    no live mirror beside, nothing to check)."""
    try:
        await client.edit_message(**kwargs)
    except (errors.FloodWaitError, errors.FloodPremiumWaitError) as e:
        logger.warning(f"{prefix}: FloodWait {e.seconds}s while fixing links — waiting it out")
        await asyncio.sleep(e.seconds)
        if edited_since is None or not await edited_since():
            await client.edit_message(**kwargs)


def history_pairs(chat_mapping: dict, drip: bool) -> Dict[Tuple[int, int], List[DirectionConfig]]:
    """The directions with ``past_mode:``, grouped by channel pair (every
    topic-direction of a pair is replayed in one pass): those with a drip
    (``drip``, the live mirror's) or the rest (this unit's). A pair goes one
    way whole — its topics share one checkpoint: a drip's when any of them
    has a pace, that one first (the pass runs at ``cfgs[0]``'s)."""
    pairs: Dict[Tuple[int, int], List[DirectionConfig]] = {}
    for src, targets in chat_mapping.items():
        for tgt, cfgs in targets.items():
            dripping = [c for c in cfgs if c.past_mode is not None and c.past_mode.drip_interval is not None]
            at_once = [c for c in cfgs if c.past_mode is not None and c.past_mode.drip_interval is None]
            if (dripping or at_once) and bool(dripping) == drip:
                pairs[(src, tgt)] = dripping + at_once
    return pairs


# The drip's own progress, FloodWaits and retries: the journal only (the live
# mirror's logger — `telemirror` — would send each to the admins); what they
# need to know (it stopped, it's done, a post skipped) is told to them.
DRIP_LOGGER = "past_mode"
# Its last line in the run's journal once every history is copied (the
# panel's ⏪ Старые посты and 📁 Проект read it: bot/routers/_units.py).
DRIP_DONE = "[PastMode] drip: done"
# In its lines when the whole drip gave up (the run's last) — the panel reads that too.
DRIP_STOPPED = "drip stopped, the live mirror goes on"
# A pair copied, its links not fixed yet (that pass comes after every pair's
# copy): its drip state's ``done`` till then — a restart doesn't go through
# the pair again, only runs that pass for it.
_LINKS_LEFT = ", links left to fix"


class _Turns:
    """A drip's one pace for the whole project: its pairs' passes run at once
    but take turns, round and round (``asyncio.Lock``: first come, first
    served) — a pass keeps the turn till it has sent a post and waited the
    interval out (what it skips costs no time), then the next pair's post."""

    def __init__(self, pairs: int) -> None:
        self.pairs = pairs
        self.done = 0  # pairs finished, for the progress line
        self.left = pairs  # pairs still taking turns (not finished, not given up), for the estimate
        self._lock = asyncio.Lock()
        self._holder: Optional[Tuple[int, int]] = None
        # last_n's scans for where their posts begin: off the turn, one at a
        # time — not every pair's at once from the one account.
        self.scan = asyncio.Lock()

    async def take(self, pair: Tuple[int, int]) -> bool:
        """True — it wasn't the pair's: taken now, maybe after the others' posts."""
        if self._holder == pair:
            return False
        await self._lock.acquire()
        self._holder = pair
        return True

    def give(self, pair: Tuple[int, int]) -> None:
        if self._holder == pair:
            self._holder = None
            self._lock.release()


async def drip_history(client: TelegramClient, database: Database, logger: logging.Logger,
                       live: Optional[EventProcessor] = None) -> None:
    """The live mirror's background task: the drip directions' history, the
    pairs taking turns at the project's one pace (🐢 Темп: a post every
    interval, from each channel in turn — not one per pair, many pairs
    flooding a target and the account), then the link-fixing pass. A pair that
    finished this very history (its strategy) isn't gone through again. Gives
    up (``logger``: the admins told) without taking the mirror down; the next
    start resumes from the checkpoints. ``live``: the mirror's processor."""
    try:
        await _drip_history(client, database, logger, live)
    except Exception as e:
        # The DB down at the start, say: the mirror only cancels this task at
        # its stop, it never looks at how it ended — said here or never.
        logger.error(f"[PastMode] {DRIP_STOPPED}. {type(e).__name__}: {e}", exc_info=True)


async def _drip_history(client: TelegramClient, database: Database, logger: logging.Logger,
                        live: Optional[EventProcessor]) -> None:
    pairs = history_pairs(CHAT_MAPPING, drip=True)
    todo, links_left, finished = {}, {}, {}
    sent_at = []
    for (src, tgt), cfgs in pairs.items():
        at, done = await database.get_drip_state(src, tgt)
        if at is not None:
            sent_at.append(at)
        label = _strategy_label(cfgs[0].past_mode)
        if done == label + _LINKS_LEFT:
            links_left[(src, tgt)] = cfgs
        elif done != label:
            todo[(src, tgt)] = cfgs
        else:
            finished[(src, tgt)] = cfgs
    quiet = logging.getLogger(DRIP_LOGGER)
    if not todo and not links_left:
        quiet.info(DRIP_DONE)  # every run says so: the panel reads this run's journal
        return
    results: List[Optional[int]] = []
    if todo:
        # A drip runs beside the live mirror: it stops at the newest message
        # there is now, at the mirror's start — everything newer is the live
        # mirror's. Regression: looked up at each pass's start, the bound took
        # in a post the live mirror was still sending (an album's wait) — sent twice.
        # Still possible for one that comes in the moments between the live
        # handlers' start and this lookup: looked up before them instead, one
        # coming in between would be neither's — lost (as `_sync_broadcast_channel`:
        # a visible duplicate rather than a silent loss).
        bounds: Dict[int, Union[int, Exception]] = {}
        for src in {src for src, _ in todo}:
            tries = 0
            while src not in bounds:
                try:
                    newest = await client.get_messages(src, limit=1)
                    bounds[src] = newest[0].id + 1 if newest else 1  # max_id is exclusive
                except (errors.FloodWaitError, errors.FloodPremiumWaitError) as e:
                    # waited out, as a pass does: the whole account waits anyway
                    quiet.warning(f"[PastMode] drip: FloodWait {e.seconds}s, waiting and retrying")
                    await asyncio.sleep(e.seconds)
                except _TRANSIENT as e:
                    tries += 1
                    if tries > _TRANSIENT_RETRY_LIMIT:
                        bounds[src] = e
                        continue
                    quiet.warning(f"[PastMode] drip: {src}'s newest post not found ({type(e).__name__}: {e}), "
                                  f"retrying in {_TRANSIENT_RETRY_WAIT}s ({tries}/{_TRANSIENT_RETRY_LIMIT})")
                    await asyncio.sleep(_TRANSIENT_RETRY_WAIT)
                except Exception as e:  # a source gone: its pairs give up, not every pair
                    bounds[src] = e
        quiet.info(f"[PastMode] drip: {len(todo)} channel pair(s) taking turns, alongside the live mirror")
        # A restart waits out the rest of the interval since the last post *any*
        # pair sent — not only the pair it resumes with (its own pass does that).
        intervals = {pm.drip_interval for cfgs in todo.values()
                     if (pm := cfgs[0].past_mode) is not None and pm.drip_interval is not None}
        if len(intervals) > 1:  # hand-written (🐢 Темп sets one for all): the longest waited here
            quiet.warning("[PastMode] drip: the directions have different paces ("
                          + ", ".join(_format_duration(i) for i in sorted(intervals))
                          + ") — each pair waits its own after its post")
        await _wait_rest(max(sent_at, default=None), max(intervals), quiet, "[PastMode] drip")
        turns = _Turns(len(todo))

        async def one(src: int, tgt: int, cfgs: List[DirectionConfig]) -> Optional[int]:
            """What the pair sent; None — it gave up (told at once; the others go
            on, it's tried again next start)."""
            try:
                bound = bounds[src]
                if isinstance(bound, Exception):  # a fresh one per pair: its traceback isn't stacked
                    raise RuntimeError(f"its newest post not found: {type(bound).__name__}: {bound}") from bound
                sent = await _replay_with_retry(client, database, src, tgt, cfgs, quiet, turns=turns,
                                                max_id=bound, live=live)
                await database.set_drip_done(src, tgt, _strategy_label(cfgs[0].past_mode) + _LINKS_LEFT)
            except Exception as e:
                # Not DRIP_STOPPED: the panel would show the whole drip stopped
                # till the next pair's post — the run's last line says it then.
                logger.error(f"[PastMode] {src}→{tgt}: gave up copying its history — the other pairs "
                             f"and the live mirror go on, tried again next start. {type(e).__name__}: {e}",
                             exc_info=True)
                return None
            finally:
                turns.give((src, tgt))
                turns.left -= 1
            turns.done += 1
            return sent

        results = await asyncio.gather(*(one(src, tgt, cfgs) for (src, tgt), cfgs in todo.items()))
    # Regression: the pairs were done before their links were fixed — a pass
    # that failed (or Telegram not giving some posts) left them unfixed for good.
    fix = {**links_left, **{pair: cfgs for (pair, cfgs), sent in zip(todo.items(), results, strict=True)
                            if sent is not None}}
    gave_up = None in results
    if todo and not gave_up:
        # Regression: links were fixed once per pair, a pair copied later (one
        # that gave up, a direction added) left the finished pairs' links to its
        # posts unfixed for good — fixed once every pair's copied (README).
        # Marked first: a restart meanwhile runs it again.
        for (src, tgt), cfgs in finished.items():
            await database.set_drip_done(src, tgt, _strategy_label(cfgs[0].past_mode) + _LINKS_LEFT)
        fix = {**finished, **fix}
    # Pair by pair: one whose links Telegram won't give (its source gone
    # private, say) doesn't keep the others' passes running every start.
    unfixed = []
    for (src, tgt), cfgs in fix.items():
        try:
            complete = await _edit_links_pass(client, database, {(src, tgt): cfgs}, quiet, beside_live=True)
        except Exception as e:
            quiet.warning(f"[PastMode] {src}→{tgt}: fixing links failed", exc_info=True)
            unfixed.append(f"{src}→{tgt}: {type(e).__name__}: {e}")
            continue
        if not complete:
            unfixed.append(f"{src}→{tgt}: some links not fixed (posts Telegram didn't give, or a network error)")
        else:  # links to a given-up pair's posts: fixed again once it's copied (`finished` above)
            await database.set_drip_done(src, tgt, _strategy_label(cfgs[0].past_mode))
    if unfixed:
        logger.error(f"[PastMode] drip: links not fixed — {DRIP_STOPPED}, tried again next start. "
                     + "; ".join(unfixed))
        return
    if gave_up:
        # The panel reads the run's last line: the other pairs' lines came after the give-up.
        quiet.warning(f"[PastMode] drip: {results.count(None)} pair(s) gave up — {DRIP_STOPPED}, "
                      "tried again next start")
        return
    quiet.info(DRIP_DONE)
    if any(results) or links_left:  # not told before: its links were left
        await _notify_done(logger)


async def _notify_done(logger: logging.Logger) -> None:
    notifier = BotNotifier.from_env(TELEMIRROR_PROJECT, "live")
    if notifier is not None and not await notifier.send("✅ Копирование истории порциями закончено."):
        logger.warning("could not tell the admins the drip is done")


async def _run(logger: logging.Logger) -> None:
    # Type=notify (telemirror-past@.service): up at once — a run with nothing
    # to replay ends before signing in, and that's not a failed start.
    sdnotify.notify("READY=1")
    pairs = history_pairs(CHAT_MAPPING, drip=False)

    if not pairs:
        if history_pairs(CHAT_MAPPING, drip=True):
            logger.warning("Every past_mode here has drip: — the live mirror copies it at that pace.")
            return
        logger.warning("No directions have past_mode configured — add past_mode: to the mirror config.")
        return

    direction_count = sum(len(c) for c in pairs.values())
    logger.info(
        f"Found {direction_count} direction(s) across {len(pairs)} channel pair(s) "
        "to replay."
    )
    logger.info(
        f"On a dropped connection: up to {_CONN_RETRIES} attempts, {_RETRY_DELAY}s apart"
    )
    database = await open_database(DB_URL, logger)
    try:
        async with open_account(
            logger, connection_retries=_CONN_RETRIES, retry_delay=_RETRY_DELAY
        ) as (client, _me):
            # A replay's own waits (FloodWait, send_delay) can last hours: the
            # watchdog checks the connection, not progress — a dead one gets
            # the unit restarted, and the replay resumes from its checkpoints.
            watchdog = asyncio.create_task(sdnotify.watchdog_loop(connection_probe(client, logger)))
            try:
                await _replay_all(client, database, pairs, logger)
            finally:
                await cancel_and_await(watchdog)
    finally:
        sdnotify.notify("STOPPING=1")
        await database.close()


async def _replay_all(client, database: Database, pairs: dict, logger: logging.Logger) -> None:
    cancel_on_sigterm()
    try:
        # Overall progress: the sum of source totals as the denominator (one
        # full pass per pair, so a source with N pairs is counted N times).
        source_total: Dict[int, int] = {}
        for src, _ in pairs:
            if src not in source_total:
                try:
                    source_total[src] = (await client.get_messages(src, limit=0)).total
                except Exception as e:
                    logger.warning(f"Failed to get total for {src}: {e}")
                    source_total[src] = 0
        overall_total = sum(source_total[src] for src, _ in pairs)
        overall_done = 0
        run_start = monotonic()

        for pair_no, ((source_id, target_id), cfgs) in enumerate(pairs.items(), start=1):
            overall_done += await _replay_with_retry(
                client, database, source_id, target_id, cfgs, logger,
                total=source_total[source_id],
            )
            _log_overall(
                logger, pair_no, len(pairs), overall_done, overall_total, run_start
            )

        # Second pass: fix cross-channel links that couldn't be resolved during mirroring
        logger.info("Second pass: fixing cross-channel links...")
        await _edit_links_pass(client, database, pairs, logger)

    except asyncio.CancelledError:
        logger.warning(
            "SIGTERM received, stopping the replay (resumable — already-mirrored "
            "messages are deduped by the DB, so resuming won't re-send them even "
            "if the checkpoint for the in-progress item wasn't reached yet)"
        )
        raise  # not a finished replay: main() exits STOPPED_EXIT


# The exit status after a SIGTERM (⏹ in the panel, the mirror started over it
# via Conflicts=): 128 + SIGTERM, as if killed by it. Not 0 — the panel tells a
# stopped replay from a finished one by it (UnitState.completed); the unit's
# SuccessExitStatus=143 keeps it a clean stop (no failed state, no OnFailure=).
STOPPED_EXIT = 143


def main() -> None:
    try:
        asyncio.run(_run(_configure_logging(LOG_LEVEL)))
    except asyncio.CancelledError:
        sys.exit(STOPPED_EXIT)


if __name__ == "__main__":
    main()
