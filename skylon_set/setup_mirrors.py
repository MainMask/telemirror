"""Setup mirrors: create, configure, verify, and build Telegram mirror configuration."""

import asyncio
import io
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml
from telethon.tl.functions.channels import (
    CreateChannelRequest,
    CreateForumTopicRequest,
    DeleteChannelRequest,
    EditForumTopicRequest,
    EditPhotoRequest,
    EditTitleRequest,
    GetForumTopicsRequest,
    ToggleForumRequest,
)
from telethon.tl.types import ChatPhotoEmpty, InputChatUploadedPhoto

from skylon_set._common import entity_type, make_client, safe_call

CONFIG_PATH = Path(__file__).resolve().parent.parent / ".configs" / "mirror.config.yml"

MENU_ACTIONS = [
    ("full-cycle",   "Полный цикл",        "создать → настроить → проверить → конфиг → финал"),
    ("create-pairs", "Создать пары",        "получателей для доноров без пары"),
    ("configure",    "Настроить",           "аватарки + эмодзи топиков + видимость General"),
    ("verify",       "Проверить",           "пары, дубли → пометить → удалить"),
    ("build-config", "Собрать конфиг",      "сгенерировать mirror.config.yml"),
    ("final-verify", "Финальная проверка",  "сверить заголовки, исправить расхождения"),
]

_SEP = "─" * 72


def show_menu() -> str:
    print("\n=== TELEMIRROR ===\n")
    action, name, desc = MENU_ACTIONS[0]
    print(f"  1. {name:<22} [{desc}]")
    print(f"  {_SEP}")
    for i, (_, name, desc) in enumerate(MENU_ACTIONS[1:], 2):
        print(f"  {i}. {name:<22} [{desc}]")
    print(f"  {_SEP}")
    print("  0. Выход\n")
    while True:
        choice = input("Выберите действие: ").strip()
        if choice == "0":
            sys.exit(0)
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(MENU_ACTIONS):
                return MENU_ACTIONS[idx][0]
        except ValueError:
            pass
        print(f"  Введите число от 0 до {len(MENU_ACTIONS)}")


# ── Утилиты ──────────────────────────────────────────────────────────────────

_DE_SKLAD_VARIANTS = ("DÈ SKLAD", "DÉ SKLAD", "DE SKLAD")


def has_de_sklad(title: str) -> bool:
    return any(v in title for v in _DE_SKLAD_VARIANTS)


def to_archonum(title: str) -> str:
    for v in _DE_SKLAD_VARIANTS:
        title = title.replace(v, "Archonum")
    return title


_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FFFF\U00002600-\U000027BF︀-️‍]+"
)


def name_key(title: str) -> str:
    """Strip brand keyword and emoji, return just the name part for fuzzy matching."""
    for v in (*_DE_SKLAD_VARIANTS, "Archonum"):
        if v in title:
            title = title.replace(v, "")
            break
    return _EMOJI_RE.sub("", title).strip()


def find_recipient(expected: str, recipients: dict):
    """Exact title match first; fall back to matching by name (brand + emoji stripped)."""
    if expected in recipients:
        return recipients[expected]
    key = name_key(expected)
    if key:
        for title, dlg in recipients.items():
            if name_key(title) == key:
                return dlg
    return None


def full_id(entity) -> int:
    return int(f"-100{entity.id}")


def get_all_donors(dialogs) -> list:
    return sorted(
        [d for d in dialogs if has_de_sklad(d.title or "")],
        key=lambda d: d.title,
    )


def build_recipient_index(dialogs) -> dict:
    """title → dialog for all Archonum-named dialogs (last wins on collision)."""
    return {d.title: d for d in dialogs if "Archonum" in (d.title or "")}


async def get_premium_status(client) -> bool:
    me = await client.get_me()
    return bool(getattr(me, "premium", False))


# ── Шаг 1: Создать пары ──────────────────────────────────────────────────────

async def step_create_pairs(client):
    print("\n=== ШАГ 1: СОЗДАНИЕ ПАР ===\n")
    dialogs = await client.get_dialogs()
    donors = get_all_donors(dialogs)
    recipients = build_recipient_index(dialogs)

    missing = []
    for donor in donors:
        expected = to_archonum(donor.title)
        dtype = entity_type(donor.entity)
        if dtype == "other":
            continue
        rec = find_recipient(expected, recipients)
        if rec and entity_type(rec.entity) == dtype:
            print(f"OK:      '{donor.title}'  →  '{expected}'")
        else:
            found = entity_type(rec.entity) if rec else None
            note = f" (найден как {found}, не как {dtype})" if found else " (не найден)"
            print(f"MISSING: '{donor.title}'  →  '{expected}'{note}")
            missing.append(donor)

    if not missing:
        print("\nВсе пары на месте.")
        return

    print(f"\nСоздаю {len(missing)} получател(ей)...")
    for donor in missing:
        new_title = to_archonum(donor.title)
        e = donor.entity
        is_broadcast = getattr(e, "broadcast", False)
        is_megagroup = getattr(e, "megagroup", False)

        if not is_broadcast and not is_megagroup:
            print(f"  ПРОПУСК '{new_title}': не канал и не супергруппа")
            continue

        kind = "канал" if is_broadcast else "супергруппу"
        print(f"  Создаю {kind} '{new_title}'...")
        result = await safe_call(client,
            lambda t=new_title, b=is_broadcast, m=is_megagroup: client(
                CreateChannelRequest(title=t, about="", broadcast=b, megagroup=m)
            )
        )
        if result is None:
            print(f"    Не удалось создать '{new_title}'")
            continue

        created = result.chats[0]
        print(f"    Создан: id={full_id(created)}  '{created.title}'")

        if is_megagroup and getattr(e, "forum", False):
            topics_result = await safe_call(client,
                lambda src=e: client(GetForumTopicsRequest(
                    channel=src, offset_date=0, offset_id=0, offset_topic=0, limit=100
                ))
            )
            if topics_result:
                print("    Включаю форум...")
                await safe_call(client,
                    lambda c=created: client(ToggleForumRequest(channel=c, enabled=True, tabs=False))
                )
                for topic in topics_result.topics:
                    if topic.id == 1:
                        continue
                    print(f"    Создаю топик '{topic.title}'...")
                    await safe_call(client,
                        lambda c=created, t=topic: client(
                            CreateForumTopicRequest(channel=c, title=t.title, icon_color=t.icon_color)
                        )
                    )

    print("Готово.")


# ── Шаг 2: Настроить ─────────────────────────────────────────────────────────

async def step_configure(client):
    print("\n=== ШАГ 2: НАСТРОЙКА ===\n")
    premium = await get_premium_status(client)
    print(f"Premium-статус: {'да' if premium else 'нет'}\n")

    dialogs = await client.get_dialogs()
    donors = get_all_donors(dialogs)
    recipients = build_recipient_index(dialogs)
    topic_cache: dict = {}

    async def fetch_topics(entity) -> dict:
        eid = entity.id
        if eid not in topic_cache:
            result = await client(GetForumTopicsRequest(
                channel=entity, offset_date=0, offset_id=0, offset_topic=0, limit=100
            ))
            topic_cache[eid] = {t.id: t for t in result.topics}
            await asyncio.sleep(0.3)
        return topic_cache[eid]

    for donor in donors:
        expected = to_archonum(donor.title)
        recipient = find_recipient(expected, recipients)
        if not recipient:
            print(f"ПРОПУСК '{donor.title}': получатель '{expected}' не найден")
            continue

        print(f"'{donor.title}'  →  '{recipient.title}'")
        d_entity = donor.entity
        r_entity = recipient.entity

        # Аватарка
        if isinstance(r_entity.photo, ChatPhotoEmpty):
            buf = io.BytesIO()
            ok = await client.download_profile_photo(d_entity, file=buf, download_big=True)
            if ok is None:
                print("  Аватарка: у донора нет")
            else:
                buf.seek(0)
                uploaded = await client.upload_file(buf, file_name="photo.jpg")
                await safe_call(client,
                    lambda re=r_entity, u=uploaded: client(
                        EditPhotoRequest(channel=re, photo=InputChatUploadedPhoto(file=u))
                    )
                )
                print("  Аватарка: скопирована")
        else:
            print("  Аватарка: уже есть")

        # Топики (только для форум-супергрупп)
        if not getattr(d_entity, "forum", False):
            continue

        d_topics = await fetch_topics(d_entity)
        r_topics = await fetch_topics(r_entity)
        r_by_title = {t.title: t for t in r_topics.values()}

        for d_topic in d_topics.values():
            r_topic = r_topics.get(1) if d_topic.id == 1 else r_by_title.get(d_topic.title)
            if not r_topic:
                print(f"  Топик '{d_topic.title}': у получателя не найден")
                continue

            # Эмодзи
            d_emoji = d_topic.icon_emoji_id or 0
            r_emoji = r_topic.icon_emoji_id or 0
            if d_emoji != r_emoji:
                if not premium and d_emoji != 0:
                    print(f"  Топик '{d_topic.title}': нет Premium для эмодзи")
                else:
                    await safe_call(client,
                        lambda re=r_entity, rid=r_topic.id, eid=d_emoji: client(
                            EditForumTopicRequest(channel=re, topic_id=rid, icon_emoji_id=eid)
                        )
                    )
                    print(f"  Топик '{d_topic.title}': эмодзи обновлён")

            # Видимость и название General
            if d_topic.id == 1:
                if d_topic.title != r_topic.title:
                    await safe_call(client,
                        lambda re=r_entity, t=d_topic.title: client(
                            EditForumTopicRequest(channel=re, topic_id=1, title=t)
                        )
                    )
                    print(f"  General: переименован в '{d_topic.title}'")
                d_hidden = bool(getattr(d_topic, "hidden", False))
                r_hidden = bool(getattr(r_topic, "hidden", False))
                if d_hidden != r_hidden:
                    await safe_call(client,
                        lambda re=r_entity, h=d_hidden: client(
                            EditForumTopicRequest(channel=re, topic_id=1, hidden=h)
                        )
                    )
                    print(f"  General: {'скрыт' if d_hidden else 'показан'}")

    print("\nНастройка завершена.")


# ── Шаг 3: Проверить ─────────────────────────────────────────────────────────

async def step_verify(client):
    print("\n=== ШАГ 3: ПРОВЕРКА ПАР И ДУБЛЕЙ ===\n")
    dialogs = await client.get_dialogs()
    donors = get_all_donors(dialogs)
    recipients = build_recipient_index(dialogs)

    # Проверка пар
    print("--- Пары ---\n")
    for donor in donors:
        expected = to_archonum(donor.title)
        dtype = entity_type(donor.entity)
        rec = find_recipient(expected, recipients)
        if rec and entity_type(rec.entity) == dtype:
            print(f"OK:      '{donor.title}'  →  '{expected}'")
        else:
            found = entity_type(rec.entity) if rec else None
            note = f" (найден как {found}, не как {dtype})" if found else " (не найден)"
            print(f"MISSING: '{donor.title}'  →  '{expected}'{note}")

    # Поиск дублей Archonum-названий
    print("\n--- Дубли ---\n")
    known_ids: set[int] = set()
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        for d in cfg.get("directions", []):
            known_ids.add(int(str(d["to"][0]).split("#")[0]))

    groups: dict[str, list] = defaultdict(list)
    for dlg in dialogs:
        title = dlg.title or ""
        if "Archonum" in title and not title.startswith("[ДУБЛЬ]"):
            groups[name_key(title)].append(dlg)

    extras = []
    any_dupe = False
    for dlgs in groups.values():
        if len(dlgs) <= 1:
            continue
        any_dupe = True
        titles = {d.title for d in dlgs}
        label = "ДУБЛЬ" if len(titles) == 1 else "ПОТЕНЦ. ДУБЛЬ"
        real  = [d for d in dlgs if full_id(d.entity) in known_ids] or dlgs[:1]
        extra = [d for d in dlgs if d not in real]
        print(f'{label}: {" / ".join(f"\"{t}\"" for t in sorted(titles))}')
        for d in real:
            print(f"  [оставить]  id={full_id(d.entity)}  '{d.title}'")
        for d in extra:
            print(f"  [лишний]    id={full_id(d.entity)}  '{d.title}'")
            extras.append(d)

    if not any_dupe:
        print("Дублей не найдено.")

    if extras:
        answer = input(f"\nПометить {len(extras)} лишних как [ДУБЛЬ]? [y/N]: ").strip().lower()
        if answer == "y":
            for dlg in extras:
                new_name = f"[ДУБЛЬ] {dlg.title}"
                print(f'  "{dlg.title}" → "{new_name}"...')
                await safe_call(client,
                    lambda e=dlg.entity, t=new_name: client(EditTitleRequest(channel=e, title=t))
                )

    # Удаление помеченных (включая уже существовавшие до этого запуска)
    marked = [d for d in await client.get_dialogs() if (d.title or "").startswith("[ДУБЛЬ]")]
    if not marked:
        print("\nОбъектов с пометкой [ДУБЛЬ] нет.")
        return

    print(f"\nНайдено {len(marked)} объект(ов) с пометкой [ДУБЛЬ]:")
    for dlg in marked:
        print(f"  {full_id(dlg.entity)}  '{dlg.title}'")

    answer = input("\nУдалить их? Это необратимо! [y/N]: ").strip().lower()
    if answer != "y":
        return

    deleted = 0
    for dlg in marked:
        print(f'  Удаляю "{dlg.title}"...')
        result = await safe_call(client, lambda e=dlg.entity: client(DeleteChannelRequest(channel=e)))
        if result is not None:
            deleted += 1
    skipped = len(marked) - deleted
    print(f"Удалено {deleted}." + (f" Пропущено {skipped} (нет доступа — удалите вручную)." if skipped else ""))


# ── Шаг 4: Собрать конфиг ────────────────────────────────────────────────────

def write_directions(config_path: Path, directions: list) -> Path | None:
    """Записывает `directions` в конфиг, сохраняя остальные ключи.

    Если файл существует — делает `.bak` и возвращает путь к нему.
    """
    config_path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    backup: Path | None = None
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            existing = yaml.safe_load(f) or {}
        backup = config_path.with_suffix(config_path.suffix + ".bak")
        backup.write_text(config_path.read_text(encoding="utf-8"), encoding="utf-8")

    existing["directions"] = directions
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            existing, f, allow_unicode=True, default_flow_style=False, sort_keys=False
        )
    return backup


async def step_build_config(client):
    print("\n=== ШАГ 4: СБОРКА КОНФИГА ===\n")
    dialogs = await client.get_dialogs()
    donors = get_all_donors(dialogs)
    recipients = build_recipient_index(dialogs)

    directions = []
    missing = []

    for donor in donors:
        e = donor.entity
        expected = to_archonum(donor.title)
        rec = find_recipient(expected, recipients)

        if not rec:
            print(f"НЕ НАЙДЕН: '{donor.title}' → '{expected}'")
            missing.append(donor.title)
            continue

        r_e = rec.entity

        if getattr(e, "broadcast", False):
            directions.append({"from": [full_id(e)], "to": [full_id(r_e)]})
            print(f"OK (канал): '{donor.title}' → '{rec.title}'")

        elif getattr(e, "megagroup", False):
            if not getattr(e, "forum", False):
                directions.append({
                    "from": [f"{full_id(e)}#1"],
                    "to":   [f"{full_id(r_e)}#1"],
                })
                print(f"OK (супергруппа): '{donor.title}' → '{rec.title}'")
                continue

            d_result = await client(GetForumTopicsRequest(
                channel=e, offset_date=0, offset_id=0, offset_topic=0, limit=100
            ))
            r_result = await client(GetForumTopicsRequest(
                channel=r_e, offset_date=0, offset_id=0, offset_topic=0, limit=100
            ))
            await asyncio.sleep(0.3)

            r_by_title = {t.title: t for t in r_result.topics}
            r_general  = next((t for t in r_result.topics if t.id == 1), None)

            for d_topic in d_result.topics:
                if d_topic.id == 1:
                    r_topic = r_general
                else:
                    r_topic = r_by_title.get(d_topic.title)

                if not r_topic:
                    print(f"  Топик '{d_topic.title}' не найден у '{rec.title}', пропускаю")
                    continue

                directions.append({
                    "from": [f"{full_id(e)}#{d_topic.id}"],
                    "to":   [f"{full_id(r_e)}#{r_topic.id}"],
                })

            print(f"OK (форум): '{donor.title}' → '{rec.title}'")

    # Обновляем только ключ `directions`, сохраняя filters / broadcast_* /
    # disable_* и прочие ручные настройки существующего конфига.
    backup = write_directions(CONFIG_PATH, directions)
    if backup:
        print(f"Бэкап прежнего конфига: {backup}")

    ch = sum(1 for d in directions if "#" not in str(d["from"][0]))
    tp = len(directions) - ch
    print(f"\nКонфиг записан: {ch} каналов + {tp} топиков → {CONFIG_PATH}")
    if missing:
        print(f"Пропущено {len(missing)} доноров без пары.")


# ── Шаг 5: Финальная проверка ─────────────────────────────────────────────────

async def step_final_verify(client):
    print("\n=== ШАГ 5: ФИНАЛЬНАЯ ПРОВЕРКА ===\n")
    if not CONFIG_PATH.exists():
        print(f"Конфиг {CONFIG_PATH} не найден. Сначала выполните шаг 4.")
        return

    with open(CONFIG_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    directions   = data.get("directions", [])
    entity_cache: dict = {}
    topic_cache:  dict = {}

    async def get_entity(chat_id: int):
        if chat_id not in entity_cache:
            entity_cache[chat_id] = await client.get_entity(chat_id)
            await asyncio.sleep(0.3)
        return entity_cache[chat_id]

    async def get_topics(chat_id: int) -> dict:
        if chat_id not in topic_cache:
            e = await get_entity(chat_id)
            result = await client(GetForumTopicsRequest(
                channel=e, offset_date=0, offset_id=0, offset_topic=0, limit=100
            ))
            topic_cache[chat_id] = {t.id: t for t in result.topics}
            await asyncio.sleep(0.3)
        return topic_cache[chat_id]

    channel_dirs = [d for d in directions if "#" not in str(d["from"][0])]
    topic_dirs   = [d for d in directions if "#" in  str(d["from"][0])]
    ok = 0
    fixes = []

    print("--- Каналы ---\n")
    for direction in channel_dirs:
        from_id = int(str(direction["from"][0]))
        to_id   = int(str(direction["to"][0]))
        from_e  = await get_entity(from_id)
        to_e    = await get_entity(to_id)
        expected = to_archonum(from_e.title)
        if to_e.title == expected:
            print(f"OK: '{from_e.title}' → '{to_e.title}'")
            ok += 1
        elif name_key(to_e.title) == name_key(expected):
            print(f"OK (эмодзи): '{from_e.title}' → '{to_e.title}'")
            ok += 1
        else:
            print(f"ОШИБКА: '{from_e.title}' → '{to_e.title}' (ожидалось '{expected}')")
            fixes.append(("channel", to_e, expected))

    print("\n--- Топики ---\n")
    for direction in topic_dirs:
        fv = str(direction["from"][0])
        tv = str(direction["to"][0])
        from_id, from_tid = int(fv.split("#")[0]), int(fv.split("#")[1])
        to_id,   to_tid   = int(tv.split("#")[0]),   int(tv.split("#")[1])

        from_topics = await get_topics(from_id)
        to_topics   = await get_topics(to_id)
        f_topic = from_topics.get(from_tid)
        t_topic = to_topics.get(to_tid)

        if not f_topic or not t_topic:
            label = f"#{from_tid} у {from_id}" if not f_topic else f"#{to_tid} у {to_id}"
            print(f"ОШИБКА: топик {label} не найден")
            fixes.append(None)
            continue

        if from_tid == 1 and to_tid == 1:
            if f_topic.title == t_topic.title:
                print(f"OK (General): '{f_topic.title}'")
                ok += 1
            else:
                print(f"ОШИБКА (General): '{f_topic.title}' != '{t_topic.title}'")
                fixes.append(("topic", entity_cache[to_id], to_tid, f_topic.title))
        elif f_topic.title == t_topic.title:
            print(f"OK: '{f_topic.title}'")
            ok += 1
        else:
            print(f"ОШИБКА: '{f_topic.title}' != '{t_topic.title}'")
            fixes.append(("topic", entity_cache[to_id], to_tid, f_topic.title))

    real_fixes = [x for x in fixes if x is not None]
    print(f"\n{'Всё верно' if not fixes else 'Есть расхождения'}: {ok} OK, {len(fixes)} ошибок.")

    if not real_fixes:
        return

    print("Исправляю расхождения...")
    for fix in real_fixes:
        if fix[0] == "channel":
            _, e, new_title = fix
            print(f"  Канал → '{new_title}'...")
            await safe_call(client,
                lambda ent=e, t=new_title: client(EditTitleRequest(channel=ent, title=t))
            )
        elif fix[0] == "topic":
            _, e, tid, new_title = fix
            print(f"  Топик #{tid} → '{new_title}'...")
            await safe_call(client,
                lambda ent=e, i=tid, t=new_title: client(
                    EditForumTopicRequest(channel=ent, topic_id=i, title=t)
                )
            )
    print("Готово.")


# ── Полный цикл ───────────────────────────────────────────────────────────────

async def run_full_cycle(client):
    await step_create_pairs(client)
    await step_configure(client)
    await step_verify(client)
    await step_build_config(client)
    await step_final_verify(client)
    print("\n=== ПОЛНЫЙ ЦИКЛ ЗАВЕРШЁН ===")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    action = show_menu()

    client = make_client()
    await client.start()

    try:
        dispatch = {
            "full-cycle":   run_full_cycle,
            "create-pairs": step_create_pairs,
            "configure":    step_configure,
            "verify":       step_verify,
            "build-config": step_build_config,
            "final-verify": step_final_verify,
        }
        await dispatch[action](client)
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
