"""Replace 🗝 with ⚜️ in all Archonum channels/supergroups and normalize spacing."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telethon import TelegramClient
from telethon.errors import ChannelPrivateError, FloodWaitError
from telethon.sessions import StringSession
from telethon.tl.functions.channels import EditTitleRequest

try:
    from config import (
        API_APP_VERSION,
        API_DEVICE_MODEL,
        API_HASH,
        API_ID,
        API_SYSTEM_VERSION,
        SESSION_STRING,
    )
except Exception:
    print("Failed reading .env")
    raise

OLD_EMOJI = "🗝"
NEW_EMOJI = "⚜️"


def entity_type(entity) -> str:
    if getattr(entity, "megagroup", False):
        return "supergroup"
    if getattr(entity, "broadcast", False):
        return "channel"
    return "other"


async def safe_call(client, fn):
    while True:
        try:
            if not client.is_connected():
                print("Переподключаюсь...")
                await client.connect()
            result = await fn()
            await asyncio.sleep(0.5)
            return result
        except FloodWaitError as e:
            print(f"FloodWait: ждём {e.seconds}с...")
            try:
                await client.disconnect()
            except Exception:
                pass
            await asyncio.sleep(e.seconds)
        except ChannelPrivateError as e:
            print(f"  Нет доступа, пропускаю: {e}")
            return None
        except (ConnectionError, OSError) as e:
            print(f"Соединение потеряно ({e}), жду 10с...")
            await asyncio.sleep(10)


def normalize_title(title: str) -> str | None:
    """Return corrected title, or None if no change needed."""
    working = title.replace(OLD_EMOJI, NEW_EMOJI)
    if NEW_EMOJI not in working or "Archonum" not in working:
        return None
    left, _, right = working.partition(NEW_EMOJI)
    _, _, after_archonum = right.partition("Archonum")
    new_title = f"{left.strip()} {NEW_EMOJI} Archonum{after_archonum.rstrip()}"
    return new_title if new_title != title else None


async def main():
    client = TelegramClient(
        StringSession(SESSION_STRING),
        API_ID,
        API_HASH,
        device_model=API_DEVICE_MODEL,
        system_version=API_SYSTEM_VERSION,
        app_version=API_APP_VERSION,
    )
    await client.start()

    print("Загружаю диалоги...")
    dialogs = await client.get_dialogs()

    archonum = [
        d for d in dialogs
        if "Archonum" in (d.title or "")
        and entity_type(d.entity) in {"channel", "supergroup"}
    ]

    renames = []
    for d in sorted(archonum, key=lambda x: x.title):
        new_title = normalize_title(d.title)
        if new_title is not None:
            renames.append((d, d.title, new_title))

    if not renames:
        print("Ничего не нужно менять.")
        await client.disconnect()
        return

    print(f"\nПланируемые переименования ({len(renames)}):\n")
    for _, old, new in renames:
        print(f"  {old!r}")
        print(f"  → {new!r}\n")

    answer = input("Применить изменения? [y/N]: ").strip().lower()
    if answer != "y":
        print("Отменено.")
        await client.disconnect()
        return

    for d, old_title, new_title in renames:
        print(f"  Переименовываю: {old_title!r} → {new_title!r} ...", end=" ")
        result = await safe_call(client, lambda e=d.entity, t=new_title: client(
            EditTitleRequest(channel=e, title=t)
        ))
        print("OK" if result is not None else "ОШИБКА")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
