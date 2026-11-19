"""Anonymizes supergroups where the account is an admin:

1. Remain Anonymous — the admin account itself becomes anonymous.
2. Hide Members — the group's member list is hidden from non-admins
   (only available for sufficiently large groups).

Broadcast channels are skipped: they have no Hide Members setting, and their
subscriber list is already hidden.

Usage:
    python -m telemirror.tasks.anonymize_groups            # with confirmation
    python -m telemirror.tasks.anonymize_groups --dry-run  # only shows the plan
    python -m telemirror.tasks.anonymize_groups --yes      # no prompt (the panel's task unit)
"""

import argparse
import asyncio
import functools

from telethon.errors import (
    ChatAdminRequiredError,
    ParticipantsTooFewError,
    RightForbiddenError,
    UserNotParticipantError,
)
from telethon.tl.functions.channels import (
    EditAdminRequest,
    GetFullChannelRequest,
    GetParticipantRequest,
    ToggleParticipantsHiddenRequest,
)
from telethon.tl.types import (
    ChannelParticipantAdmin,
    ChannelParticipantCreator,
    ChatAdminRights,
)

from telemirror.account import open_account
from telemirror.config import LOG_LEVEL
from telemirror.misc.log_setup import setup_stdout_logger
from telemirror.tasks._common import entity_type
from telemirror.tasks._common import safe_call as _safe_call

# EditAdmin/GetParticipant/toggles also fail with these when the account lacks the
# right admin permissions — treat as "skip", like a private channel.
safe_call = functools.partial(
    _safe_call,
    skip_errors=(ChatAdminRequiredError, RightForbiddenError, UserNotParticipantError),
)


def get_rights(rights: ChatAdminRights | None) -> ChatAdminRights:
    if rights is None:
        return ChatAdminRights(anonymous=True, other=True)
    return ChatAdminRights(
        change_info=rights.change_info,
        post_messages=rights.post_messages,
        edit_messages=rights.edit_messages,
        delete_messages=rights.delete_messages,
        ban_users=rights.ban_users,
        invite_users=rights.invite_users,
        pin_messages=rights.pin_messages,
        add_admins=rights.add_admins,
        anonymous=True,
        manage_call=rights.manage_call,
        other=rights.other,
        manage_topics=getattr(rights, "manage_topics", None),
        post_stories=getattr(rights, "post_stories", None),
        edit_stories=getattr(rights, "edit_stories", None),
        delete_stories=getattr(rights, "delete_stories", None),
        manage_direct_messages=getattr(rights, "manage_direct_messages", None),
    )


async def get_admin_participant(client, entity, me):
    """Return (participant, is_anonymous) or None if not admin."""
    result = await safe_call(
        client,
        lambda: client(GetParticipantRequest(channel=entity, participant=me)),
    )
    if result is None:
        return None
    p = result.participant
    if isinstance(p, ChannelParticipantCreator):
        rights = p.admin_rights
        # admin_rights is None when creator has all rights implicitly → treat as not anonymous
        return (p, bool(rights and getattr(rights, "anonymous", False)))
    if isinstance(p, ChannelParticipantAdmin):
        return (p, bool(p.admin_rights.anonymous))
    return None


def _titles(lst):
    return ", ".join(d.title for d in lst) if lst else "—"


async def apply_anonymous(client, me, admin_of, dry_run=False, assume_yes=False):
    """Pass 1: Remain Anonymous for the account in every group where it's an admin."""
    print("\n=== Remain Anonymous ===")
    already = [d for d, _p, is_anon in admin_of if is_anon]
    targets = [(d, p) for d, p, is_anon in admin_of if not is_anon]

    print(f"Already anonymous ({len(already)}):    {_titles(already)}")
    print(f"Need activation ({len(targets)}): {_titles([d for d, _ in targets])}")

    if not targets:
        print("The account is already anonymous in every group where it's an admin.")
        return

    if dry_run:
        print(f"(dry-run) Would activate it in {len(targets)} group(s).")
        return

    if not assume_yes:
        answer = input(
            f"\nActivate Remain Anonymous in {len(targets)} group(s)? [y/N]: "
        ).strip().lower()
        if answer != "y":
            print("Skipped.")
            return

    for d, participant in targets:
        print(f"  {d.title} ...", end=" ", flush=True)
        new_rights = get_rights(participant.admin_rights)
        rank = getattr(participant, "rank", None) or ""
        result = await safe_call(
            client,
            lambda e=d.entity, r=new_rights, rk=rank: client(
                EditAdminRequest(channel=e, user_id=me, admin_rights=r, rank=rk)
            ),
        )
        print("OK" if result is not None else "ERROR")

    print("\nVerification:")
    errors = []
    for d, _ in targets:
        info = await get_admin_participant(client, d.entity, me)
        if info and info[1]:
            print(f"  OK: {d.title}")
        else:
            print(f"  ERROR: {d.title}")
            errors.append(d.title)
    if errors:
        print(f"Failed to activate in {len(errors)} group(s): {', '.join(errors)}")
    else:
        print("All OK — Remain Anonymous activated in every group.")


async def _participants_hidden(client, entity) -> bool | None:
    """Current Hide Members state; None — couldn't be read."""
    result = await safe_call(client, lambda: client(GetFullChannelRequest(entity)))
    if result is None:
        return None
    return bool(result.full_chat.participants_hidden)


async def apply_hide_members(client, admin_of, dry_run=False, assume_yes=False):
    """Pass 2: Hide Members in every group where the account is an admin."""
    print("\n=== Hide Members ===")
    already, targets, unknown = [], [], []
    for d, _p, _is_anon in admin_of:
        state = await _participants_hidden(client, d.entity)
        if state is None:
            unknown.append(d)
        elif state:
            already.append(d)
        else:
            targets.append(d)

    print(f"Already hidden ({len(already)}):        {_titles(already)}")
    print(f"Need enabling ({len(targets)}): {_titles(targets)}")
    print(f"Could not read ({len(unknown)}):      {_titles(unknown)}")

    if not targets:
        print("The member list is already hidden in every group.")
        return

    if dry_run:
        print(f"(dry-run) Would hide it in {len(targets)} group(s).")
        return

    if not assume_yes:
        answer = input(
            f"\nHide the member list in {len(targets)} group(s)? [y/N]: "
        ).strip().lower()
        if answer != "y":
            print("Skipped.")
            return

    too_few = []
    for d in targets:
        print(f"  {d.title} ...", end=" ", flush=True)
        try:
            result = await safe_call(
                client,
                lambda e=d.entity: client(
                    ToggleParticipantsHiddenRequest(channel=e, enabled=True)
                ),
            )
            print("OK" if result is not None else "ERROR")
        except ParticipantsTooFewError:
            too_few.append(d.title)
            print("too few members — setting unavailable")

    print("\nVerification:")
    errors = []
    for d in targets:
        if d.title in too_few:
            continue
        if await _participants_hidden(client, d.entity):
            print(f"  OK: {d.title}")
        else:
            print(f"  ERROR: {d.title}")
            errors.append(d.title)
    if too_few:
        print(f"Skipped (too few members): {', '.join(too_few)}")
    if errors:
        print(f"Failed to hide in {len(errors)} group(s): {', '.join(errors)}")
    elif not too_few:
        print("All OK — member list hidden in every group.")


async def _run(logger, dry_run: bool, assume_yes: bool = False):
    # open_account: the session lock and a clear error instead of a login
    # prompt (there's no terminal under the panel's task unit).
    async with open_account(logger) as (client, me):
        print("Loading dialogs...")
        dialogs = await client.get_dialogs()
        supergroups = [d for d in dialogs if entity_type(d.entity) == "supergroup"]
        print(f"{len(supergroups)} supergroup(s) found.")

        admin_of = []  # [(dialog, participant, is_anonymous)]
        not_admin = []
        for d in supergroups:
            info = await get_admin_participant(client, d.entity, me)
            if info is None:
                not_admin.append(d)
            else:
                admin_of.append((d, info[0], info[1]))
        print(f"Not an admin ({len(not_admin)}): {_titles(not_admin)}")

        await apply_anonymous(client, me, admin_of, dry_run, assume_yes)
        await apply_hide_members(client, admin_of, dry_run, assume_yes)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m telemirror.tasks.anonymize_groups",
        description="Remain Anonymous + Hide Members in every supergroup the account admins"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only show the plan, without making real changes",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Don't ask for confirmation (non-interactive runs, e.g. the panel's task unit)",
    )
    args = parser.parse_args()

    logger = setup_stdout_logger("anonymize_groups", LOG_LEVEL)
    try:
        asyncio.run(_run(logger, args.dry_run, args.yes))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
