"""Одноразовый: сборка mirror-конфига «⚜️ Цитадель».

Сопоставляет каналы/форумы-доноры их получателям «⚜️ Цитадель», создаёт
недостающие топики-копии в двух получателях-супергруппах и печатает блок
``directions:`` для вставки в ``.configs/mirror.config.yml`` (у каждой директории
``past_mode: full_history``). Идемпотентен: существующие топики переиспользуются,
скрипт можно перезапускать после обрыва по FloodWait.
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from config import LOG_LEVEL
except Exception:
    print("Failed reading .env")
    raise

import yaml
from telethon import utils
from telethon.tl.functions.messages import CreateForumTopicRequest, GetForumTopicsRequest

from skylon_set._common import configure_logging, make_client, safe_call

# донор → получатель
CHANNEL_PAIRS = [
    (-1003007946025, -1004382220692),  # Адептус🪐            → Адептус ⚜️ Цитадель
    (-1002738411064, -1003930417508),  # Sigma Male Grindset 🇯🇵 → … ⚜️ Цитадель
    (-1002919476953, -1004492144131),  # Баzza Арсена Маркаряна → … ⚜️ Цитадель
    (-1003453434923, -1004335381593),  # Галактика «Окситоцин»  → … ⚜️ Цитадель
    (-1003442453098, -1004461404658),  # Детский сад «Базовичок» → … ⚜️ Цитадель
    (-1003026483451, -1004453577173),  # Портал между мирами    → … ⚜️ Цитадель
]

FORUM_PAIRS = [
    (-1003983984082, -1004458106126),  # GRIND UNIVERSITY 3.0 → GRIND UNIVERSITY 3.0 ⚜️ Цитадель
    (-1002307710800, -1004310135623),  # O Λ И M П            → Цитадель ⚜️ Премиум
]

PAST_MODE = {"full_history": True}


async def fetch_topics(client, chat_id):
    out, off_d, off_id, off_t = [], 0, 0, 0
    while True:
        r = await client(GetForumTopicsRequest(
            peer=chat_id, offset_date=off_d, offset_id=off_id, offset_topic=off_t, limit=100
        ))
        out.extend(r.topics)
        await asyncio.sleep(0.3)
        if len(r.topics) < 100:
            return out
        last = r.topics[-1]
        off_t, off_id, off_d = last.id, last.top_message, getattr(last, "date", 0) or 0


async def sync_topics(client, donor_id, recip_id, premium, logger):
    """Создаёт у получателя каждый топик донора (id != 1), отсутствующий по названию."""
    donor_topics = await fetch_topics(client, donor_id)
    recip_titles = {t.title for t in await fetch_topics(client, recip_id)}

    for t in donor_topics:
        if t.id == 1 or t.title in recip_titles:
            continue
        emoji = t.icon_emoji_id or 0
        kwargs = {"title": t.title}
        if premium and emoji:
            kwargs["icon_emoji_id"] = emoji
        else:
            kwargs["icon_color"] = t.icon_color
        logger.info(f"  + топик {t.title!r}")
        await safe_call(client, lambda k=kwargs: client(CreateForumTopicRequest(peer=recip_id, **k)))


async def build_forum_directions(client, donor_id, recip_id):
    donor_topics = await fetch_topics(client, donor_id)
    recip_topics = await fetch_topics(client, recip_id)
    recip_by_title = {t.title: t.id for t in recip_topics}

    directions, missing = [], []
    for t in donor_topics:
        to_tid = 1 if t.id == 1 else recip_by_title.get(t.title)
        if to_tid is None:
            missing.append(t.title)
            continue
        directions.append({
            "from": [f"{donor_id}#{t.id}"],
            "to": [f"{recip_id}#{to_tid}"],
            "past_mode": PAST_MODE,
        })
    return directions, missing


async def _run(logger: logging.Logger) -> None:
    logger.warning(
        "setup_citadel.py использует тот же SESSION_STRING, что и main.py. "
        "Убедитесь, что main.py НЕ запущен."
    )

    client = make_client(flood_sleep_threshold=60)
    client.parse_mode = "markdown"
    await client.connect()

    try:
        me = await client.get_me()
        if me is None:
            raise RuntimeError(
                "Нет авторизации. Запустите login.py для получения SESSION_STRING."
            )
        at_username = f" (@{me.username})" if getattr(me, "username", None) else ""
        logger.info(f"Вошли как {utils.get_display_name(me)}{at_username}")
        premium = bool(getattr(me, "premium", False))
        logger.info(f"Premium: {'да' if premium else 'нет'}")

        logger.info("=== Создание топиков-копий ===")
        for donor_id, recip_id in FORUM_PAIRS:
            logger.info(f"{donor_id} → {recip_id}")
            await sync_topics(client, donor_id, recip_id, premium, logger)

        logger.info("=== Сборка directions ===")
        directions = [
            {"from": [d], "to": [r], "past_mode": PAST_MODE}
            for d, r in CHANNEL_PAIRS
        ]
        for donor_id, recip_id in FORUM_PAIRS:
            dirs, missing = await build_forum_directions(client, donor_id, recip_id)
            directions.extend(dirs)
            logger.info(
                f"{donor_id} → {recip_id}: {len(dirs)} топиков"
                + (f", не сопоставлено: {missing}" if missing else "")
            )

        class _NoAlias(yaml.SafeDumper):
            def ignore_aliases(self, data):
                return True

        block = yaml.dump(
            {"directions": directions}, Dumper=_NoAlias,
            allow_unicode=True, default_flow_style=False, sort_keys=False,
        )
        ch = len(CHANNEL_PAIRS)
        logger.info(
            f"{ch} каналов + {len(directions) - ch} топиков — "
            "вставьте блок ниже вместо `directions:` в .configs/mirror.config.yml"
        )
        print("\n" + block)
    finally:
        await client.disconnect()


def main() -> None:
    logger = configure_logging("setup_citadel", LOG_LEVEL)
    try:
        asyncio.run(_run(logger))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
