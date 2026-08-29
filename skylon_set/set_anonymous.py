"""Activate Remain Anonymous for the account in all supergroups where it's an admin."""

import asyncio
import functools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telethon.errors import (
    ChatAdminRequiredError,
    RightForbiddenError,
    UserNotParticipantError,
)
from telethon.tl.functions.channels import EditAdminRequest, GetParticipantRequest
from telethon.tl.types import (
    ChannelParticipantAdmin,
    ChannelParticipantCreator,
    ChatAdminRights,
)

from skylon_set._common import entity_type, make_client
from skylon_set._common import safe_call as _safe_call

# EditAdmin/GetParticipant also fail with these when the account lacks the right
# admin permissions — treat as "skip", like a private channel.
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


async def main():
    client = make_client()
    await client.start()

    me = await client.get_me()
    name = me.first_name or ""
    if me.username:
        name += f" (@{me.username})"
    print(f"Аккаунт: {name}")

    print("Загружаю диалоги...")
    dialogs = await client.get_dialogs()
    supergroups = [d for d in dialogs if entity_type(d.entity) == "supergroup"]
    print(f"{len(supergroups)} supergroups найдено.\n")

    already_anon = []
    targets = []
    not_admin = []

    for d in supergroups:
        info = await get_admin_participant(client, d.entity, me)
        if info is None:
            not_admin.append(d)
        elif info[1]:
            already_anon.append(d)
        else:
            targets.append((d, info[0]))

    def titles(lst):
        return ", ".join(d.title for d in lst) if lst else "—"

    print(f"Уже анонимны ({len(already_anon)}):    {titles(already_anon)}")
    print(f"Требуют активации ({len(targets)}): {titles([d for d, _ in targets])}")
    print(f"Не администратор ({len(not_admin)}):  {titles(not_admin)}")

    if not targets:
        print("\nАккаунт уже анонимен везде, где является администратором.")
        await client.disconnect()
        return

    answer = input(f"\nАктивировать Remain Anonymous в {len(targets)} группах? [y/N]: ").strip().lower()
    if answer != "y":
        print("Отменено.")
        await client.disconnect()
        return

    print()
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
        print("OK" if result is not None else "ОШИБКА")

    print("\nПроверка:")
    errors = []
    for d, _ in targets:
        info = await get_admin_participant(client, d.entity, me)
        if info and info[1]:
            print(f"  OK: {d.title}")
        else:
            print(f"  ОШИБКА: {d.title}")
            errors.append(d.title)

    if not errors:
        print("\nВсё OK — Remain Anonymous активирован во всех группах.")
    else:
        print(f"\nНе удалось активировать в {len(errors)} группах: {', '.join(errors)}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
