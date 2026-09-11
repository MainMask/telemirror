"""Copies donor channels'/supergroups' pinned messages onto the matching
mirrors at the recipients.

The "donor pin id → mirror id" link comes from the ``binding_id`` table, which
``past_mode.py`` populates (needs a persistent Postgres DB). Pinning a mirror
that lives in a forum topic is done by Telegram inside that topic
automatically — no topic mapping is needed here.

By default the mode is reconcile: whatever the donor unpinned is also unpinned
at the recipient, but only among messages the mirror itself created
(``managed_ids``). A user's manual pins (with no ``binding_id`` row) are left
alone. ``--additive`` disables unpinning.

The donor's pin order is reproduced exactly only on a clean first run (an
incremental diff does not reorder pins that already exist).

Usage (while main.py is STOPPED — shared SESSION_STRING):
    python -m skylon_set.sync_pins --dry-run
    python -m skylon_set.sync_pins --only -1003007946025
    python -m skylon_set.sync_pins            # live run across every pair

On a large forum the first run may hit a FloodWait while pinning —
``safe_call`` waits those out, so the run can take several minutes.
"""

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from config import BROADCAST_CHANNEL, CHAT_MAPPING, DB_URL, LOG_LEVEL, USE_MEMORY_DB
except Exception:
    print("Failed reading .env")
    raise

from telethon import errors
from telethon.tl import types
from telethon.tl.functions.messages import SearchRequest, UpdatePinnedMessageRequest
from telethon.tl.types import InputMessagesFilterPinned

from telemirror.misc.links import private_message_link
from telemirror.misc.log_setup import setup_stdout_logger
from telemirror.storage import MirrorMessage, PostgresDatabase
from skylon_set._common import open_client, safe_call


# ── Values ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SyncPair:
    donor_id: int
    recipient_id: int
    topic_map: Dict[int, int]  # from_topic_id → to_topic_id ({} for a channel pair)

    @property
    def from_topics(self) -> List[int]:
        return sorted(self.topic_map)

    @property
    def to_topics(self) -> List[int]:
        return sorted(set(self.topic_map.values()))


@dataclass(frozen=True)
class PinPlan:
    to_pin: List[int]    # mirror id, order: oldest → newest
    to_unpin: List[int]  # mirror id


@dataclass
class PairSummary:
    donor_id: int
    recipient_id: int
    desired: int = 0
    already_pinned: int = 0
    pinned: int = 0
    unpinned: int = 0
    skipped_no_binding: int = 0
    dupes: List[int] = field(default_factory=list)


# ── Pure functions ───────────────────────────────────────────────────────────

def iter_sync_directions(
    chat_mapping: Dict[int, Dict[int, list]],
    broadcast_channel: Optional[int],
    include_broadcast: bool = False,
) -> List[SyncPair]:
    """CHAT_MAPPING → list of donor→recipient pairs.

    A pair whose DONOR is the broadcast channel is skipped (unless
    include_broadcast): its posts fan out to every target, and copying an
    admin pin into 8 unrelated channels usually isn't wanted. Being a
    broadcast RECIPIENT is not a reason to exclude a pair.
    """
    pairs: List[SyncPair] = []
    for donor_id, tgt_map in chat_mapping.items():
        if donor_id == broadcast_channel and not include_broadcast:
            continue
        for recipient_id, cfgs in tgt_map.items():
            topic_map = {
                c.from_topic_id: c.to_topic_id
                for c in cfgs
                if c.from_topic_id is not None
            }
            pairs.append(
                SyncPair(
                    donor_id=donor_id,
                    recipient_id=recipient_id,
                    topic_map=topic_map,
                )
            )
    return pairs


def build_pin_map(
    rows: List[MirrorMessage],
) -> Tuple[Dict[int, int], List[int]]:
    """rows from get_messages_for_channel_pair → ({original_id: mirror_id}, [dupes]).

    When several different mirror_ids exist for one original_id, the smallest
    is used (determinism), and original_id is added to the dupes list.
    """
    grouped: Dict[int, Set[int]] = {}
    for r in rows:
        grouped.setdefault(r.original_id, set()).add(r.mirror_id)
    pin_map = {oid: min(mids) for oid, mids in grouped.items()}
    dupes = sorted(oid for oid, mids in grouped.items() if len(mids) > 1)
    return pin_map, dupes


def resolve_desired_pins(
    donor_pins: Sequence["types.Message"],
    pin_map: Dict[int, int],
    logger: logging.Logger,
    label: str,
) -> Tuple[List[int], int]:
    """Donor pins → list of mirror_id (in donor_pins order).

    Donor pins with no binding_id row (message was dropped by a mirroring
    filter / a service message / older than past_mode's range) are skipped.
    Returns (mirror_ids, skipped_no_binding).
    """
    desired: List[int] = []
    skipped = 0
    for msg in donor_pins:
        mirror_id = pin_map.get(msg.id)
        if mirror_id is None:
            skipped += 1
            logger.info(
                f"[{label}] donor pin has no mirror, skipping: "
                f"{private_message_link(msg.chat_id, msg.id)}"
            )
            continue
        desired.append(mirror_id)
    return desired, skipped


def plan_pin_actions(
    desired: Sequence[int],
    current_pinned_ids: Set[int],
    managed_ids: Set[int],
    *,
    reconcile: bool,
    allow_clear: bool = False,
) -> PinPlan:
    desired_set = set(desired)
    to_pin = sorted(desired_set - current_pinned_ids)  # ascending ≈ oldest first
    if not reconcile:
        return PinPlan(to_pin, [])
    stale = (current_pinned_ids & managed_ids) - desired_set
    if not desired_set and stale and not allow_clear:
        # The donor suddenly has zero pins — more likely a fetch failure than
        # a genuine mass-unpin. Leave it alone until --allow-clear is passed.
        return PinPlan(to_pin, [])
    return PinPlan(to_pin, sorted(stale))


# ── I/O ──────────────────────────────────────────────────────────────────────

async def fetch_pinned(
    client,
    peer: int,
    topic_ids: Optional[Sequence[int]],
    max_pins: int,
    thorough: bool,
    logger: logging.Logger,
) -> List["types.Message"]:
    """A peer's pinned messages: a general pass over the whole chat + (with
    --thorough) a targeted pass per topic. Merged by id.
    """
    by_id: Dict[int, "types.Message"] = {}

    whole = await safe_call(
        client,
        lambda: client.get_messages(
            peer, filter=InputMessagesFilterPinned(), limit=None
        ),
    )
    if whole is None:
        logger.warning(f"[{peer}] no access to pins, skipping")
        return []
    for m in whole:
        by_id[m.id] = m

    if thorough and topic_ids:
        for tid in topic_ids:
            res = await safe_call(
                client,
                lambda t=tid: client(
                    SearchRequest(
                        peer=peer,
                        q="",
                        filter=InputMessagesFilterPinned(),
                        min_date=None,
                        max_date=None,
                        offset_id=0,
                        add_offset=0,
                        limit=max_pins,
                        max_id=0,
                        min_id=0,
                        hash=0,
                        top_msg_id=t,
                    )
                ),
            )
            if res is None:
                continue
            if len(res.messages) == max_pins:
                logger.warning(
                    f"[{peer}#{tid}] got exactly {max_pins} pin(s) back — "
                    f"possibly truncated, raise --max-pins"
                )
            for m in res.messages:
                by_id.setdefault(m.id, m)

    return list(by_id.values())


async def sync_pair(
    client,
    db: PostgresDatabase,
    pair: SyncPair,
    *,
    reconcile: bool,
    allow_clear: bool,
    max_pins: int,
    thorough: bool,
    dry_run: bool,
    logger: logging.Logger,
) -> PairSummary:
    label = f"{pair.donor_id}→{pair.recipient_id}"
    summary = PairSummary(pair.donor_id, pair.recipient_id)

    rows = await db.get_messages_for_channel_pair(pair.donor_id, pair.recipient_id)
    pin_map, dupes = build_pin_map(rows)
    summary.dupes = dupes
    if dupes:
        logger.warning(f"[{label}] duplicate binding_id rows for original_id: {dupes}")
    if not pin_map:
        logger.warning(
            f"[{label}] no rows in binding_id — run past_mode.py first, skipping pair"
        )
        return summary

    managed_ids = {r.mirror_id for r in rows}

    donor_pins = await fetch_pinned(
        client, pair.donor_id, pair.from_topics or None, max_pins, thorough, logger
    )
    desired, skipped = resolve_desired_pins(donor_pins, pin_map, logger, label)
    summary.desired = len(desired)
    summary.skipped_no_binding = skipped

    current_pins = await fetch_pinned(
        client, pair.recipient_id, pair.to_topics or None, max_pins, thorough, logger
    )
    current_ids = {m.id for m in current_pins}
    summary.already_pinned = len(set(desired) & current_ids)

    plan = plan_pin_actions(
        desired, current_ids, managed_ids, reconcile=reconcile, allow_clear=allow_clear
    )

    if not dry_run:
        # Pin in ascending mirror_id order (oldest → newest). On a clean first
        # run this puts the donor's newest pin on top; on a re-run with
        # existing pins, the exact order isn't reproduced.
        for mid in plan.to_pin:
            await safe_call(
                client,
                lambda m=mid: client(
                    UpdatePinnedMessageRequest(
                        peer=pair.recipient_id, id=m, silent=True
                    )
                ),
                skip_errors=(errors.MessageIdInvalidError,),
            )
        for mid in plan.to_unpin:
            await safe_call(
                client,
                lambda m=mid: client(
                    UpdatePinnedMessageRequest(
                        peer=pair.recipient_id, id=m, unpin=True, silent=True
                    )
                ),
                skip_errors=(errors.MessageIdInvalidError,),
            )

    summary.pinned = len(plan.to_pin)
    summary.unpinned = len(plan.to_unpin)
    suffix = " (dry-run)" if dry_run else ""
    logger.info(
        f"[{label}] desired={summary.desired} already={summary.already_pinned} "
        f"pinned=+{summary.pinned} unpinned=-{summary.unpinned} "
        f"no-binding={summary.skipped_no_binding}{suffix}"
    )
    return summary


async def _run(logger: logging.Logger, args: argparse.Namespace) -> None:
    logger.warning(
        "sync_pins.py uses the same SESSION_STRING as main.py. "
        "Make sure main.py is NOT running."
    )

    if USE_MEMORY_DB:
        logger.error(
            "USE_MEMORY_DB=true — there are no bindings. Set up Postgres and "
            "run past_mode.py first."
        )
        return

    pairs = iter_sync_directions(CHAT_MAPPING, BROADCAST_CHANNEL, args.include_broadcast)
    if args.only:
        wanted = set(args.only)
        pairs = [p for p in pairs if p.donor_id in wanted]
    if not pairs:
        logger.warning("No pairs to synchronize.")
        return

    logger.info(f"Pairs to synchronize: {len(pairs)}")

    db = await PostgresDatabase(connection_string=DB_URL)
    try:
        async with open_client(
            logger, warn_main_running=False, flood_sleep_threshold=60
        ) as (client, _me):
            # A raw SearchRequest needs the peer resolved from the session — warm the cache.
            peer_ids = {p.donor_id for p in pairs} | {p.recipient_id for p in pairs}
            for cid in peer_ids:
                await safe_call(
                    client, lambda c=cid: client.get_entity(c), skip_errors=(ValueError,)
                )

            totals = PairSummary(0, 0)
            for pair in pairs:
                try:
                    s = await sync_pair(
                        client,
                        db,
                        pair,
                        reconcile=not args.additive,
                        allow_clear=args.allow_clear,
                        max_pins=args.max_pins,
                        thorough=args.thorough,
                        dry_run=args.dry_run,
                        logger=logger,
                    )
                except Exception as e:
                    logger.error(
                        f"[{pair.donor_id}→{pair.recipient_id}] error: "
                        f"{type(e).__name__}: {e}"
                    )
                    continue
                totals.desired += s.desired
                totals.pinned += s.pinned
                totals.unpinned += s.unpinned
                totals.skipped_no_binding += s.skipped_no_binding

            suffix = " (dry-run)" if args.dry_run else ""
            logger.info(
                f"Total: desired={totals.desired} pinned=+{totals.pinned} "
                f"unpinned=-{totals.unpinned} no-binding={totals.skipped_no_binding}{suffix}"
            )
    finally:
        await db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Synchronize pinned messages from donor to recipient"
    )
    parser.add_argument("--dry-run", action="store_true", help="Only show the plan")
    parser.add_argument(
        "--additive",
        action="store_true",
        help="Only pin what's missing, never unpin",
    )
    parser.add_argument(
        "--allow-clear",
        action="store_true",
        help="Allow unpinning every managed pin when the donor has none left",
    )
    parser.add_argument(
        "--include-broadcast",
        action="store_true",
        help="Also synchronize the broadcast channel's pins",
    )
    parser.add_argument(
        "--thorough",
        action="store_true",
        help="Additionally poll pins per forum topic",
    )
    parser.add_argument("--max-pins", type=int, default=100)
    parser.add_argument(
        "--only",
        type=int,
        action="append",
        metavar="DONOR_ID",
        help="Restrict to the given donors (repeatable)",
    )
    args = parser.parse_args()

    logger = setup_stdout_logger("sync_pins", LOG_LEVEL)
    try:
        asyncio.run(_run(logger, args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
