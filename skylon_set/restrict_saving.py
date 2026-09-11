"""
Enables "Restrict Saving Content" (the ``noforwards`` flag — blocks
subscribers from copying/forwarding content) on every recipient channel and
supergroup: live ones (CHAT_MAPPING from mirror.config.yml) and course ones
(citadel_courses.config.yml, which config.py itself does not read).

Usage:
    python -m skylon_set.restrict_saving            # with confirmation
    python -m skylon_set.restrict_saving --dry-run  # only shows the plan

Warning: uses the same SESSION_STRING as the main service.
Do not run at the same time as main.py.
"""

import argparse
import asyncio
import functools
import logging
import sys
from pathlib import Path
from typing import Set

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from config import CHAT_MAPPING, LOG_LEVEL
except Exception:
    print("Failed reading .env")
    raise

import yaml
from telethon.errors import ChatAdminRequiredError, RightForbiddenError
from telethon.tl.functions.messages import ToggleNoForwardsRequest

from telemirror.misc.log_setup import setup_stdout_logger
from skylon_set._common import open_client
from skylon_set._common import safe_call as _safe_call

# config.py does not load the courses config (only past_mode.py reads it), but
# Restrict Saving is needed on course recipients too — read the ids straight
# from the file, the same way setup_mirrors.step_final_verify does.
COURSES_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / ".configs" / "citadel_courses.config.yml"
)

# ToggleNoForwards fails with these when the account isn't admin of a recipient —
# treat as "skip", like a private channel (same handling as anonymize_groups.py).
safe_call = functools.partial(
    _safe_call, skip_errors=(ChatAdminRequiredError, RightForbiddenError)
)


def collect_recipient_ids(chat_mapping) -> Set[int]:
    """Collects the set of recipient channel ids from CHAT_MAPPING.

    Topics don't matter — ``noforwards`` is set at the chat level.
    """
    return {tgt_id for tgt_map in chat_mapping.values() for tgt_id in tgt_map}


def course_recipient_ids(path: Path = COURSES_CONFIG_PATH) -> Set[int]:
    """Recipient ids from citadel_courses.config.yml (empty if the file is absent)."""
    if not path.exists():
        return set()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        int(str(target).split("#")[0])
        for direction in data.get("directions", [])
        for target in direction.get("to", [])
    }


async def _run(logger: logging.Logger, dry_run: bool) -> None:
    recipient_ids = collect_recipient_ids(CHAT_MAPPING) | course_recipient_ids()
    if not recipient_ids:
        logger.warning("CHAT_MAPPING is empty — nothing to configure.")
        return

    async with open_client(logger) as (client, _me):
        already, targets, unavailable = [], [], []
        for chat_id in sorted(recipient_ids):
            try:
                entity = await safe_call(
                    client, lambda i=chat_id: client.get_entity(i)
                )
            except Exception as e:
                logger.error(f"[{chat_id}] failed to fetch entity: {e}")
                entity = None
            if entity is None:
                unavailable.append(chat_id)
            elif getattr(entity, "noforwards", False):
                already.append(entity)
            else:
                targets.append(entity)

        def titles(lst):
            return ", ".join(getattr(e, "title", str(e)) for e in lst) if lst else "—"

        logger.info(f"Already enabled ({len(already)}):     {titles(already)}")
        logger.info(f"Need enabling ({len(targets)}): {titles(targets)}")
        logger.info(f"Unavailable ({len(unavailable)}):      {unavailable or '—'}")

        if not targets:
            logger.info("Restrict Saving Content is already enabled for every recipient.")
            return

        if dry_run:
            logger.info(
                f"(dry-run) Would enable it in {len(targets)} chat(s)."
            )
            return

        answer = input(
            f"\nEnable Restrict Saving Content in {len(targets)} chat(s)? [y/N] "
        ).strip().lower()
        if answer != "y":
            logger.info("Cancelled.")
            return

        for entity in targets:
            result = await safe_call(
                client,
                lambda e=entity: client(
                    ToggleNoForwardsRequest(peer=e, enabled=True)
                ),
            )
            logger.info(
                f"  {getattr(entity, 'title', str(entity))}: "
                + ("OK" if result is not None else "ERROR")
            )

        errors = []
        for entity in targets:
            fresh = await safe_call(
                client, lambda e=entity: client.get_entity(e)
            )
            if not (fresh and getattr(fresh, "noforwards", False)):
                errors.append(getattr(entity, "title", str(entity)))

        if errors:
            logger.error(
                f"Failed to enable it in {len(errors)} chat(s): {', '.join(errors)}"
            )
        else:
            logger.info("All OK — Restrict Saving Content enabled for every recipient.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enable Restrict Saving Content on telemirror's recipients"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only show the plan, without making real changes",
    )
    args = parser.parse_args()

    logger = setup_stdout_logger("restrict_saving", LOG_LEVEL)
    try:
        asyncio.run(_run(logger, args.dry_run))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
