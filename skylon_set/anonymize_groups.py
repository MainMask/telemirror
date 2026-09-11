"""Анонимизирует супергруппы, где аккаунт — админ:

1. Remain Anonymous — сам аккаунт-админ становится анонимным.
2. Hide Members — список участников группы скрывается от неадминов
   (доступно только для достаточно крупных групп).

Broadcast-каналы пропускаются: настройки Hide Members у них нет, а список
подписчиков и так скрыт.
"""

import asyncio
import functools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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

from skylon_set._common import entity_type, make_client
from skylon_set._common import safe_call as _safe_call

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


async def apply_anonymous(client, me, admin_of):
    """Проход 1: Remain Anonymous для аккаунта в каждой группе, где он админ."""
    print("\n=== Remain Anonymous ===")
    already = [d for d, _p, is_anon in admin_of if is_anon]
    targets = [(d, p) for d, p, is_anon in admin_of if not is_anon]

    print(f"Уже анонимен ({len(already)}):    {_titles(already)}")
    print(f"Требуют активации ({len(targets)}): {_titles([d for d, _ in targets])}")

    if not targets:
        print("Аккаунт уже анонимен во всех группах, где является администратором.")
        return

    answer = input(
        f"\nАктивировать Remain Anonymous в {len(targets)} группах? [y/N]: "
    ).strip().lower()
    if answer != "y":
        print("Пропущено.")
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
    if errors:
        print(f"Не удалось активировать в {len(errors)} группах: {', '.join(errors)}")
    else:
        print("Всё OK — Remain Anonymous активирован во всех группах.")


async def _participants_hidden(client, entity) -> bool | None:
    """Текущее состояние Hide Members; None — не удалось прочитать."""
    result = await safe_call(client, lambda: client(GetFullChannelRequest(entity)))
    if result is None:
        return None
    return bool(result.full_chat.participants_hidden)


async def apply_hide_members(client, admin_of):
    """Проход 2: Hide Members в каждой группе, где аккаунт админ."""
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

    print(f"Уже скрыты ({len(already)}):        {_titles(already)}")
    print(f"Требуют включения ({len(targets)}): {_titles(targets)}")
    print(f"Не прочитано ({len(unknown)}):      {_titles(unknown)}")

    if not targets:
        print("Список участников уже скрыт во всех группах.")
        return

    answer = input(
        f"\nСкрыть список участников в {len(targets)} группах? [y/N]: "
    ).strip().lower()
    if answer != "y":
        print("Пропущено.")
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
            print("OK" if result is not None else "ОШИБКА")
        except ParticipantsTooFewError:
            too_few.append(d.title)
            print("мало участников — настройка недоступна")

    print("\nПроверка:")
    errors = []
    for d in targets:
        if d.title in too_few:
            continue
        if await _participants_hidden(client, d.entity):
            print(f"  OK: {d.title}")
        else:
            print(f"  ОШИБКА: {d.title}")
            errors.append(d.title)
    if too_few:
        print(f"Пропущено (мало участников): {', '.join(too_few)}")
    if errors:
        print(f"Не удалось скрыть в {len(errors)} группах: {', '.join(errors)}")
    elif not too_few:
        print("Всё OK — список участников скрыт во всех группах.")


async def main():
    client = make_client()
    await client.start()
    try:
        me = await client.get_me()
        name = me.first_name or ""
        if me.username:
            name += f" (@{me.username})"
        print(f"Аккаунт: {name}")

        print("Загружаю диалоги...")
        dialogs = await client.get_dialogs()
        supergroups = [d for d in dialogs if entity_type(d.entity) == "supergroup"]
        print(f"{len(supergroups)} supergroups найдено.")

        admin_of = []  # [(dialog, participant, is_anonymous)]
        not_admin = []
        for d in supergroups:
            info = await get_admin_participant(client, d.entity, me)
            if info is None:
                not_admin.append(d)
            else:
                admin_of.append((d, info[0], info[1]))
        print(f"Не администратор ({len(not_admin)}): {_titles(not_admin)}")

        await apply_anonymous(client, me, admin_of)
        await apply_hide_members(client, admin_of)
    finally:
        await client.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
