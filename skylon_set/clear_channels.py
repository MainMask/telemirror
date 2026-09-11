"""
Deletes every message in every recipient channel and supergroup topic
described in the config (CHAT_MAPPING).

Usage:
    python clear_channels.py           # with confirmation
    python clear_channels.py --dry-run # only shows the targets

Warning: uses the same SESSION_STRING as the main service.
Do not run at the same time as main.py.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Dict, Optional, Set

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from config import CHAT_MAPPING, DB_URL, LOG_LEVEL, USE_MEMORY_DB
except Exception:
    print("Failed reading .env")
    raise

from telethon import TelegramClient
from telethon.tl.functions.channels import DeleteHistoryRequest

from telemirror.misc.log_setup import setup_stdout_logger
from telemirror.misc.topics import topic_id_of
from telemirror.storage import PostgresDatabase
from skylon_set._common import open_client, safe_call

DELETE_BATCH = 100


def collect_targets(chat_mapping) -> Dict[int, Set[Optional[int]]]:
    """Collects {channel_id: set(topic_ids)} from CHAT_MAPPING's target channels."""
    targets: Dict[int, Set[Optional[int]]] = {}
    for tgt_map in chat_mapping.values():
        for tgt_id, cfgs in tgt_map.items():
            for cfg in cfgs:
                targets.setdefault(tgt_id, set()).add(cfg.to_topic_id)
    return targets


def channels_for_full_clear(targets: Dict[int, Set[Optional[int]]]) -> list:
    """Channels with no topic scoping — only these can be cleared wholesale
    via DeleteHistory."""
    return [channel_id for channel_id, topic_ids in targets.items() if None in topic_ids]


async def purge(
    client: TelegramClient,
    channel_id: int,
    topic_ids: Set[int],
    dry_run: bool,
    logger: logging.Logger,
) -> int:
    """Deletes messages from the given topics of a channel in a single history pass.

    Used to be called once per topic — K full passes over the channel's
    history; now a single pass routes messages to the topics that matter.
    """
    label = f"{channel_id} topics {sorted(topic_ids)}"
    deleted = 0
    batch: list = []

    async def flush():
        nonlocal deleted
        if not batch:
            return
        if not dry_run:
            await safe_call(
                client,
                lambda ids=list(batch): client.delete_messages(channel_id, ids),
            )
        deleted += len(batch)
        batch.clear()

    async for msg in client.iter_messages(channel_id):
        if msg.action is not None:  # MessageService (channel created, pin, etc.) — skip
            continue
        if topic_id_of(msg) not in topic_ids:
            continue
        batch.append(msg.id)
        if len(batch) >= DELETE_BATCH:
            await flush()

    await flush()

    action = "Found (dry-run)" if dry_run else "Deleted"
    logger.info(f"[{label}] {action}: {deleted} message(s)")
    return deleted


async def _reset_db_state(
    cleared_targets: Dict[int, Set[Optional[int]]],
    dry_run: bool,
    logger: logging.Logger,
) -> None:
    """Resets past_mode checkpoints and binding_id rows for the cleared target channels."""
    pairs = [
        (src, tgt)
        for src, tgt_map in CHAT_MAPPING.items()
        for tgt in tgt_map
        if tgt in cleared_targets
    ]
    target_ids = list(cleared_targets)

    if dry_run:
        logger.info(
            f"(dry-run) Would reset {len(pairs)} checkpoint(s) and clear "
            f"binding_id for {len(target_ids)} channel(s)"
        )
        return

    if USE_MEMORY_DB:
        return  # in-memory state doesn't survive a restart

    db = await PostgresDatabase(connection_string=DB_URL)
    try:
        for src, tgt in pairs:
            await db.delete_past_mode_checkpoint(src, tgt)
            logger.info(f"[checkpoint] reset: {src}→{tgt}")
        for tgt in target_ids:
            await db.delete_bindings_for_mirror(tgt)
            logger.info(f"[binding_id] cleared: {tgt}")
    finally:
        await db.close()


async def _run(logger: logging.Logger, dry_run: bool) -> None:
    logger.warning(
        "clear_channels.py uses the same SESSION_STRING as the live service. "
        "Make sure main.py is NOT running."
    )

    targets = collect_targets(CHAT_MAPPING)
    if not targets:
        logger.warning("CHAT_MAPPING is empty — nothing to clear.")
        return

    # Channels without topic scoping are cleared wholesale via DeleteHistory —
    # their history isn't scanned. The rest get one pass per channel over
    # their set of topics.
    full_clear = set(channels_for_full_clear(targets))
    topic_only = {
        channel_id: {t for t in topic_ids if t is not None}
        for channel_id, topic_ids in targets.items()
        if channel_id not in full_clear
    }

    logger.info(
        f"Targets: {len(topic_only)} topic-scoped + {len(full_clear)} full clear"
    )
    for channel_id, tids in topic_only.items():
        logger.info(f"  {channel_id} topics {sorted(tids)}")
    for channel_id in full_clear:
        logger.info(f"  {channel_id} (DeleteHistory)")

    if not dry_run:
        answer = input("\nProceed with deletion? [y/N] ").strip().lower()
        if answer != "y":
            logger.info("Cancelled.")
            return

    total = 0
    # Only channels that were actually cleared (or would be, in dry-run) get
    # their DB state reset — a channel whose purge/DeleteHistory call failed
    # must keep its checkpoint, or a later past_mode/live run would think it's
    # starting clean and re-mirror everything into a channel that still has
    # the old (un-deleted) messages, duplicating content.
    cleared: Dict[int, Set[Optional[int]]] = {}
    async with open_client(
        logger, warn_main_running=False, flood_sleep_threshold=60
    ) as (client, _me):
        for channel_id, tids in topic_only.items():
            try:
                total += await purge(client, channel_id, tids, dry_run, logger)
                cleared[channel_id] = targets[channel_id]
            except Exception as e:
                logger.error(f"[{channel_id}] Error: {e}")

        if dry_run:
            logger.info(
                f"(dry-run) DeleteHistory would be called for {len(full_clear)} channel(s)"
            )
            cleared.update({channel_id: targets[channel_id] for channel_id in full_clear})
        else:
            for channel_id in full_clear:
                try:
                    await client(DeleteHistoryRequest(
                        channel=channel_id, max_id=0, for_everyone=True
                    ))
                    logger.info(f"[{channel_id}] DeleteHistory done")
                    cleared[channel_id] = targets[channel_id]
                except Exception as e:
                    logger.error(f"[{channel_id}] DeleteHistory error: {e}")

        await _reset_db_state(cleared, dry_run, logger)

    action = "Found (dry-run)" if dry_run else "Total deleted"
    logger.info(f"{action}: {total} message(s) (topic-scoped channels).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Clear telemirror's recipient channels")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only show what would be deleted, without deleting anything",
    )
    args = parser.parse_args()

    logger = setup_stdout_logger("purge_targets", LOG_LEVEL)
    try:
        asyncio.run(_run(logger, args.dry_run))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
