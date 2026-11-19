"""
Read-only check of the account's access to every chat the config names: it
must see each source and the broadcast channel, and be able to post in each
recipient. Changes nothing.

Usage:
    python -m telemirror.tasks.check_access

Run as a project (TELEMIRROR_PROJECT, the panel's task unit) it also writes the
report to projects/<key>/access.json for the panel's 🛂 Проверка доступа screen.

Warning: uses the same session as the main service.
"""

import asyncio
import json
import logging
import time
from typing import Dict, Optional, Set

from telethon import utils

from telemirror.account import open_account
from telemirror.config import (
    BROADCAST_CHANNEL,
    CHAT_MAPPING,
    LOG_LEVEL,
    TELEMIRROR_PROJECT,
)
from telemirror.misc.log_setup import setup_stdout_logger
from telemirror.projects import access_report_path, save_chat_names
from telemirror.tasks._common import safe_call

POST_ROLES = ("target",)  # the account must post in these (and see the rest)


def collect_roles(chat_mapping, broadcast: Optional[int]) -> Dict[int, Set[str]]:
    """{chat_id: roles} of every chat the config names."""
    roles: Dict[int, Set[str]] = {}
    for src, tgt_map in chat_mapping.items():
        roles.setdefault(src, set()).add("broadcast" if src == broadcast else "source")
        for tgt in tgt_map:
            roles.setdefault(tgt, set()).add("target")
    if broadcast is not None:
        roles.setdefault(broadcast, set()).add("broadcast")
    return roles


def can_post(entity) -> bool:
    """From the account's own view of the chat (dialog entity): a channel needs
    the creator or an admin with post_messages; a group — not banned from sending."""
    if getattr(entity, "creator", False):
        return True
    rights = getattr(entity, "admin_rights", None)
    if getattr(entity, "broadcast", False):
        return bool(rights and rights.post_messages)
    if rights is not None:
        return True
    for banned in (getattr(entity, "banned_rights", None), getattr(entity, "default_banned_rights", None)):
        if banned is not None and banned.send_messages:
            return False
    return True


def check_chat(chat_id: int, roles: Set[str], entity) -> dict:
    row = {"id": chat_id, "roles": sorted(roles), "title": None, "ok": True, "reason": "", "note": ""}
    if entity is None:
        row.update(ok=False, reason="not_member")
        return row
    row["title"] = utils.get_display_name(entity)
    if roles & set(POST_ROLES) and not can_post(entity):
        row.update(ok=False, reason="cannot_post")
    if "source" in roles and getattr(entity, "noforwards", False):
        row["note"] = "noforwards"
    return row


async def _run(logger: logging.Logger) -> dict:
    roles = collect_roles(CHAT_MAPPING, BROADCAST_CHANNEL)
    if not roles:
        logger.warning("CHAT_MAPPING is empty — nothing to check.")
    async with open_account(logger) as (client, _me):
        # The account's own dialogs: the entities carry its rights in each chat,
        # and a chat missing from them is one it isn't a member of.
        dialogs = await safe_call(client, lambda: client.get_dialogs()) or []
        entities = {utils.get_peer_id(d.entity): d.entity for d in dialogs}
    rows = [check_chat(chat_id, r, entities.get(chat_id)) for chat_id, r in sorted(roles.items())]
    for row in rows:
        status = "OK" if row["ok"] else f"PROBLEM ({row['reason']})"
        note = f" [{row['note']}]" if row["note"] else ""
        logger.info(f"{row['id']} {','.join(row['roles'])} — {row['title'] or '?'}: {status}{note}")
    bad = sum(1 for row in rows if not row["ok"])
    logger.info(f"Checked {len(rows)} chat(s): {len(rows) - bad} OK, {bad} with problems.")
    report = {"at": time.time(), "chats": rows}
    if TELEMIRROR_PROJECT:
        path = access_report_path(TELEMIRROR_PROJECT)
        tmp = path.with_name(f".{path.name}.tmp")
        tmp.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(path)
        save_chat_names(TELEMIRROR_PROJECT, {row["id"]: row["title"] for row in rows if row["title"]})
    return report


def main() -> None:
    logger = setup_stdout_logger("check_access", LOG_LEVEL)
    try:
        asyncio.run(_run(logger))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
