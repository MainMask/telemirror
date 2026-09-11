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
    DeleteChannelRequest,
    EditPhotoRequest,
    EditTitleRequest,
    ToggleForumRequest,
)
from telethon.tl.functions.messages import (
    CreateForumTopicRequest,
    EditForumTopicRequest,
)
from telethon.tl.types import ChatPhotoEmpty, InputChatUploadedPhoto

from skylon_set._common import entity_type, fetch_all_topics, make_client, safe_call

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

_CITADEL_SUFFIX = "⚜️ Цитадель"
_PIRATE_FLAG = "🏴‍☠️"

# «🏴‍☠️ DÈ SKLAD» в хвосте заголовка (флаг и пробелы опциональны).
_DONOR_TRAILER_RE = re.compile(
    r"\s*(?:" + re.escape(_PIRATE_FLAG) + r"\s*)?(?:"
    + "|".join(re.escape(v) for v in _DE_SKLAD_VARIANTS)
    + r")\s*$"
)


def has_de_sklad(title: str) -> bool:
    return any(v in title for v in _DE_SKLAD_VARIANTS)


def to_citadel(title: str) -> str:
    """Заголовок донора → заголовок получателя.

    Срезает хвост «🏴‍☠️ DÈ SKLAD» и дописывает «⚜️ Цитадель». Заголовки без хвоста
    (например «Activity | …») просто получают суффикс.
    """
    return f"{_DONOR_TRAILER_RE.sub('', title).rstrip()} {_CITADEL_SUFFIX}"


_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FFFF\U00002600-\U000027BF︀-️‍]+"
)


def name_key(title: str) -> str:
    """Strip brand keyword and emoji, return just the name part for fuzzy matching."""
    for v in (*_DE_SKLAD_VARIANTS, "Цитадель"):
        if v in title:
            title = title.replace(v, "")
            break
    return _EMOJI_RE.sub("", title).strip()


# ── Классификация доноров: живые (past + live) vs курсы (только past_mode) ─────
#
# Имена — как в диалогах владельца. Живые остаются в .configs/mirror.config.yml;
# курсы уходят в отдельный citadel_courses.config.yml, который читает только
# past_mode.py. Всё, что нашлось по «DE SKLAD», но не попало ни в один список,
# скрипт печатает и не трогает.

_LIVE_DONOR_TITLES = [
    "СЛЕЗЫ САТОШИ 🏴‍☠️ DÈ SKLAD",
    "BILLIONS CRYPTO 🏴‍☠️ DÈ SKLAD",
    "pepe.research 🏴‍☠️ DÈ SKLAD",
    "CRYPTO ANGEL 🏴‍☠️ DÈ SKLAD",
    "INSTARDING 🏴‍☠️ DÉ SKLAD",
    "MM TRADERS 🏴‍☠️ DÈ SKLAD",
    "VECTRUM CLUB 🏴‍☠️DÈ SKLAD",
    "INSTARDING PRO TRADING 🏴‍☠️ DÉ SKLAD",
    "shitpost padre 🏴‍☠️ DÉ SKLAD",
    "Pentagon Pro 🏴‍☠️ DE SKLAD",
    "SmartCapital 🏴‍☠️ DÈ SKLAD",
    "Rose 🏴‍☠️ DÈ SKLAD",
]

_COURSE_DONOR_TITLES = [
    "Maloletoff Education 2024 🏴‍☠️ DÈ SKLAD",
    "CRYPTOLOGY 🏴‍☠️ DÈ SKLAD",
    "SANCHO 🏴‍☠️ DÈ SKLAD",
    "Jay Education 🏴‍☠️ DÈ SKLAD",
    "Mozart Academy 🏴‍☠️ DÈ SKLAD",
    "Cryptomannn 2023 🏴‍☠️ DÈ SKLAD",
    "a01k Academy 🏴‍☠️ DÈ SKLAD",
    "Activity | Начинающий дропхантер",
    "MM ACADEMY 🏴‍☠️ DÈ SKLAD",
    "Block13 🏴‍☠️ DÈ SKLAD",
    "CRYPTOLOGY WORKSHOP 🏴‍☠️ DÈ SKLAD",
    "DEXMEN EDUCATION 🏴‍☠️ DÈ SKLAD",
    "Meme bootcamp 2.0 🏴‍☠️ DÈ SKLAD",
    "DYOR Pentagon 5.0 🏴‍☠️ DÉ SKLAD",
    "DAYTRADING ACADEMY 🏴‍☠️ DÈ SKLAD",
    "Vectrum Обучение 🏴‍☠️ DÈ SKLAD",
    "DeFi Crypto 🏴‍☠️ DÈ SKLAD",
    "Activity | Курс для новичков 2024",
    "Обучение от КОВЧЕГА 🏴‍☠️ DÈ SKLAD",
    "A01K Academy 2.0 🏴‍☠️ DÉ SKLAD",
    "DarkTrader 3.0 🏴‍☠️ DÈ SKLAD",
    "Dyor Pentagon Education 🏴‍☠️ DÈ SKLAD",
    "Meme bootcamp (ноябрь) 🏴‍☠️ DÈ SKLAD",
]

_LIVE_KEYS = {name_key(t).casefold() for t in _LIVE_DONOR_TITLES}
_COURSE_KEYS = {name_key(t).casefold() for t in _COURSE_DONOR_TITLES}
assert _LIVE_KEYS.isdisjoint(_COURSE_KEYS), (
    f"живые и курсы пересеклись: {_LIVE_KEYS & _COURSE_KEYS}"
)


def classify_donor(title: str) -> str:
    """«live» / «course» / «unknown» по спискам выше (сверка по name_key).

    Уже созданные получатели «⚜️ Цитадель» никогда не доноры: их name_key
    совпадает с донорским, поэтому исключаем по бренду в заголовке.
    """
    if "Цитадель" in title:
        return "unknown"
    key = name_key(title).casefold()
    if key in _LIVE_KEYS:
        return "live"
    if key in _COURSE_KEYS:
        return "course"
    return "unknown"


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
    """Доноры из хардкод-списков (живые + курсы), найденные среди диалогов."""
    return sorted(
        [d for d in dialogs if classify_donor(d.title or "") != "unknown"],
        key=lambda d: d.title or "",
    )


def report_unmatched(dialogs) -> None:
    """Печатает «DE SKLAD»-диалоги, которых нет ни в одном списке (не трогаются)."""
    unmatched = [
        d.title
        for d in dialogs
        if has_de_sklad(d.title or "") and classify_donor(d.title or "") == "unknown"
    ]
    if unmatched:
        print(f"\nВне списков ({len(unmatched)}, пропускаю):")
        for title in sorted(unmatched):
            print(f"  ? '{title}'")


def build_recipient_index(dialogs) -> dict:
    """title → dialog for all «Цитадель»-named dialogs (last wins on collision)."""
    return {d.title: d for d in dialogs if "Цитадель" in (d.title or "")}


async def get_premium_status(client) -> bool:
    me = await client.get_me()
    return bool(getattr(me, "premium", False))


# ── Шаг 1: Создать пары ──────────────────────────────────────────────────────

async def _sync_forum_topics(client, donor_e, recip_e, *, enable_forum: bool) -> None:
    """Создаёт у получателя каждый топик донора (id != 1), которого нет по названию.

    Идемпотентно: повторный запуск после обрыва по FloodWait дозаполняет топики.
    """
    if enable_forum:
        print("    Включаю форум...")
        await safe_call(client,
            lambda: client(ToggleForumRequest(channel=recip_e, enabled=True, tabs=False))
        )

    donor_topics = await fetch_all_topics(client, donor_e)
    recip_titles = {t.title for t in await fetch_all_topics(client, recip_e)}
    for topic in donor_topics:
        if topic.id == 1 or topic.title in recip_titles:
            continue
        print(f"    Создаю топик '{topic.title}'...")
        await safe_call(client,
            lambda t=topic: client(
                CreateForumTopicRequest(peer=recip_e, title=t.title, icon_color=t.icon_color)
            )
        )


async def step_create_pairs(client):
    print("\n=== ШАГ 1: СОЗДАНИЕ ПАР ===\n")
    dialogs = await client.get_dialogs()
    donors = get_all_donors(dialogs)
    recipients = build_recipient_index(dialogs)
    report_unmatched(dialogs)

    missing = []
    for donor in donors:
        expected = to_citadel(donor.title)
        dtype = entity_type(donor.entity)
        if dtype == "other":
            continue
        rec = find_recipient(expected, recipients)
        if rec and entity_type(rec.entity) == dtype:
            print(f"OK:      '{donor.title}'  →  '{expected}'")
            # получатель мог остаться без части топиков (обрыв прошлого запуска)
            if getattr(donor.entity, "forum", False):
                if getattr(rec.entity, "forum", False):
                    await _sync_forum_topics(
                        client, donor.entity, rec.entity, enable_forum=False
                    )
                else:
                    print("    ⚠ получатель не форум — топики не синхронизированы")
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
        new_title = to_citadel(donor.title)
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
            await _sync_forum_topics(client, e, created, enable_forum=True)

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
            topic_cache[eid] = {
                t.id: t for t in await fetch_all_topics(client, entity)
            }
        return topic_cache[eid]

    for donor in donors:
        expected = to_citadel(donor.title)
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
                            EditForumTopicRequest(peer=re, topic_id=rid, icon_emoji_id=eid)
                        )
                    )
                    print(f"  Топик '{d_topic.title}': эмодзи обновлён")

            # Видимость и название General
            if d_topic.id == 1:
                if d_topic.title != r_topic.title:
                    await safe_call(client,
                        lambda re=r_entity, t=d_topic.title: client(
                            EditForumTopicRequest(peer=re, topic_id=1, title=t)
                        )
                    )
                    print(f"  General: переименован в '{d_topic.title}'")
                d_hidden = bool(getattr(d_topic, "hidden", False))
                r_hidden = bool(getattr(r_topic, "hidden", False))
                if d_hidden != r_hidden:
                    await safe_call(client,
                        lambda re=r_entity, h=d_hidden: client(
                            EditForumTopicRequest(peer=re, topic_id=1, hidden=h)
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
        expected = to_citadel(donor.title)
        dtype = entity_type(donor.entity)
        kind = classify_donor(donor.title)
        rec = find_recipient(expected, recipients)
        if rec and entity_type(rec.entity) == dtype:
            print(f"OK      [{kind}]: '{donor.title}'  →  '{expected}'")
        else:
            found = entity_type(rec.entity) if rec else None
            note = f" (найден как {found}, не как {dtype})" if found else " (не найден)"
            print(f"MISSING [{kind}]: '{donor.title}'  →  '{expected}'{note}")

    report_unmatched(dialogs)

    # Поиск дублей «Цитадель»-названий
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
        key = name_key(title)
        # пустой ключ = заголовок ровно «Цитадель» (бренд вырезан целиком):
        # такие каналы схлопнулись бы в одну ложную группу
        if key and "Цитадель" in title and not title.startswith("[ДУБЛЬ]"):
            groups[key].append(dlg)

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

def _direction(frm, to) -> dict:
    """Одно направление с `past_mode: full_history` (свежий dict — без YAML-алиасов)."""
    return {"from": [frm], "to": [to], "past_mode": {"full_history": True}}


def _dir_key(d: dict) -> tuple:
    return (
        tuple(str(x) for x in d["from"]),
        tuple(str(x) for x in d["to"]),
    )


def _append_directions_text(config_path: Path, original: str, fresh: list) -> None:
    """Дописать `fresh` в конец блока `directions:`, сохраняя комментарии файла.

    Требует, чтобы `directions:` был последним ключом верхнего уровня (так в
    .configs/mirror.config.yml).
    """
    lines = original.splitlines()
    top_keys = [i for i, ln in enumerate(lines) if re.match(r"[A-Za-z_][\w-]*:", ln)]
    if not top_keys or not lines[top_keys[-1]].startswith("directions:"):
        raise ValueError(
            "directions: не последний ключ верхнего уровня — дозапись небезопасна, "
            "правьте конфиг вручную"
        )
    block = yaml.safe_dump(
        fresh, allow_unicode=True, default_flow_style=False, sort_keys=False
    )
    sep = "" if original.endswith("\n") else "\n"
    config_path.write_text(original + sep + block, encoding="utf-8")


def write_directions(
    config_path: Path, directions: list, *, merge: bool = False
) -> Path | None:
    """Записывает `directions` в конфиг, сохраняя остальные ключи.

    `merge=False` (умолч.) — заменяет ключ `directions` целиком (комментарии файла
    теряются). `merge=True` — дописывает только новые направления (дедуп по
    from→to) в конец блока `directions:` текстом, сохраняя комментарии.

    Если файл существует — делает `.bak` и возвращает путь к нему.
    """
    config_path.parent.mkdir(parents=True, exist_ok=True)

    if not config_path.exists():
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                {"directions": directions}, f,
                allow_unicode=True, default_flow_style=False, sort_keys=False,
            )
        return None

    original = config_path.read_text(encoding="utf-8")
    backup = config_path.with_suffix(config_path.suffix + ".bak")
    backup.write_text(original, encoding="utf-8")

    if not merge:
        existing = yaml.safe_load(original) or {}
        existing["directions"] = directions
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                existing, f,
                allow_unicode=True, default_flow_style=False, sort_keys=False,
            )
        return backup

    existing = yaml.safe_load(original) or {}
    seen = {_dir_key(d) for d in (existing.get("directions") or [])}
    fresh = [d for d in directions if _dir_key(d) not in seen]
    if not fresh:
        backup.unlink()
        return None
    _append_directions_text(config_path, original, fresh)
    return backup


COURSES_CONFIG_PATH = CONFIG_PATH.parent / "citadel_courses.config.yml"


def write_courses_config(course_dirs: list) -> Path | None:
    """Пишет citadel_courses.config.yml: глобальный блок из mirror.config.yml
    (без broadcast_*) + directions курсов. Файл читает только past_mode.py."""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        main_cfg = yaml.safe_load(f) or {}
    carry = {
        k: main_cfg[k]
        for k in ("disable_edit", "disable_delete", "fallback_link_url", "filters")
        if k in main_cfg
    }
    carry["directions"] = course_dirs

    backup: Path | None = None
    if COURSES_CONFIG_PATH.exists():
        backup = COURSES_CONFIG_PATH.with_suffix(COURSES_CONFIG_PATH.suffix + ".bak")
        backup.write_text(
            COURSES_CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8"
        )

    header = (
        "# Сгенерировано skylon_set/setup_mirrors.py — курсы «⚜️ Цитадель».\n"
        "# main.py этот файл НЕ читает; курсы только прогоняются по истории:\n"
        '#   YAML_CONFIG_ENV="$(cat .configs/citadel_courses.config.yml)" python past_mode.py\n\n'
    )
    body = yaml.safe_dump(
        carry, allow_unicode=True, default_flow_style=False, sort_keys=False
    )
    COURSES_CONFIG_PATH.write_text(header + body, encoding="utf-8")
    return backup


async def step_build_config(client):
    print("\n=== ШАГ 4: СБОРКА КОНФИГА ===\n")
    dialogs = await client.get_dialogs()
    donors = get_all_donors(dialogs)
    recipients = build_recipient_index(dialogs)

    live_dirs: list = []
    course_dirs: list = []
    missing = []

    for donor in donors:
        e = donor.entity
        expected = to_citadel(donor.title)
        rec = find_recipient(expected, recipients)
        kind = classify_donor(donor.title)
        bucket = live_dirs if kind == "live" else course_dirs

        if not rec:
            print(f"НЕ НАЙДЕН [{kind}]: '{donor.title}' → '{expected}'")
            missing.append(donor.title)
            continue

        r_e = rec.entity

        if getattr(e, "broadcast", False):
            bucket.append(_direction(full_id(e), full_id(r_e)))
            print(f"OK (канал) [{kind}]: '{donor.title}' → '{rec.title}'")

        elif getattr(e, "megagroup", False):
            if not getattr(e, "forum", False):
                bucket.append(_direction(f"{full_id(e)}#1", f"{full_id(r_e)}#1"))
                print(f"OK (супергруппа) [{kind}]: '{donor.title}' → '{rec.title}'")
                continue

            d_topics = await fetch_all_topics(client, e)
            r_topics = await fetch_all_topics(client, r_e)

            r_by_title = {t.title: t for t in r_topics}
            r_general  = next((t for t in r_topics if t.id == 1), None)

            for d_topic in d_topics:
                if d_topic.id == 1:
                    r_topic = r_general
                else:
                    r_topic = r_by_title.get(d_topic.title)

                if not r_topic:
                    print(f"  Топик '{d_topic.title}' не найден у '{rec.title}', пропускаю")
                    continue

                bucket.append(_direction(
                    f"{full_id(e)}#{d_topic.id}", f"{full_id(r_e)}#{r_topic.id}"
                ))

            print(f"OK (форум) [{kind}]: '{donor.title}' → '{rec.title}'")

    report_unmatched(dialogs)

    # Живые — дозапись в основной конфиг (комментарии и текущие направления целы).
    live_backup = write_directions(CONFIG_PATH, live_dirs, merge=True)
    if live_backup:
        print(f"\nЖивые: дозаписано в {CONFIG_PATH} (бэкап: {live_backup})")
    else:
        print(f"\nЖивые: новых направлений нет, {CONFIG_PATH} не тронут")

    # Курсы — отдельный файл только для past_mode.py.
    if course_dirs:
        courses_backup = write_courses_config(course_dirs)
        note = f" (бэкап: {courses_backup})" if courses_backup else ""
        print(f"Курсы: {len(course_dirs)} направлений → {COURSES_CONFIG_PATH}{note}")

    for label, dirs in (("живые", live_dirs), ("курсы", course_dirs)):
        ch = sum(1 for d in dirs if "#" not in str(d["from"][0]))
        print(f"  {label}: {ch} каналов + {len(dirs) - ch} топиков")
    if missing:
        print(f"Пропущено {len(missing)} доноров без пары: {missing}")


# ── Шаг 5: Финальная проверка ─────────────────────────────────────────────────

async def step_final_verify(client):
    print("\n=== ШАГ 5: ФИНАЛЬНАЯ ПРОВЕРКА ===\n")
    if not CONFIG_PATH.exists():
        print(f"Конфиг {CONFIG_PATH} не найден. Сначала выполните шаг 4.")
        return

    with open(CONFIG_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    directions   = list(data.get("directions", []))
    if COURSES_CONFIG_PATH.exists():
        with open(COURSES_CONFIG_PATH, encoding="utf-8") as f:
            directions += (yaml.safe_load(f) or {}).get("directions", [])
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
            topic_cache[chat_id] = {
                t.id: t for t in await fetch_all_topics(client, e)
            }
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
        if classify_donor(from_e.title or "") == "unknown":
            continue  # чужое направление (прежние пачки) — не наша забота
        to_e    = await get_entity(to_id)
        expected = to_citadel(from_e.title)
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

        from_e = await get_entity(from_id)
        if classify_donor(from_e.title or "") == "unknown":
            continue  # чужое направление (прежние пачки) — не наша забота
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
                    EditForumTopicRequest(peer=ent, topic_id=i, title=t)
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
