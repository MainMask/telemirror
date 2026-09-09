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
from telethon.tl.functions.messages import CreateForumTopicRequest

from telemirror.misc.log_setup import setup_stdout_logger
from skylon_set._common import fetch_all_topics, open_client, safe_call

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


async def sync_topics(client, recip_id, premium, logger, donor_topics, recip_topics):
    """Создаёт у получателя каждый топик донора (id != 1), отсутствующий по названию."""
    recip_titles = {t.title for t in recip_topics}

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


def build_forum_directions(donor_id, recip_id, donor_topics, recip_topics):
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
    async with open_client(logger, flood_sleep_threshold=60) as (client, me):
        premium = bool(getattr(me, "premium", False))
        logger.info(f"Premium: {'да' if premium else 'нет'}")

        logger.info("=== Создание топиков-копий ===")
        donor_topics_by_id = {}
        for donor_id, recip_id in FORUM_PAIRS:
            logger.info(f"{donor_id} → {recip_id}")
            donor_topics = await fetch_all_topics(client, donor_id)
            recip_topics = await fetch_all_topics(client, recip_id)
            donor_topics_by_id[donor_id] = donor_topics
            await sync_topics(
                client, recip_id, premium, logger, donor_topics, recip_topics
            )

        logger.info("=== Сборка directions ===")
        directions = [
            {"from": [d], "to": [r], "past_mode": PAST_MODE}
            for d, r in CHANNEL_PAIRS
        ]
        for donor_id, recip_id in FORUM_PAIRS:
            # топики получателя перечитываем — sync_topics мог создать новые;
            # донор не меняется, берём из первого прохода
            recip_topics = await fetch_all_topics(client, recip_id)
            dirs, missing = build_forum_directions(
                donor_id, recip_id, donor_topics_by_id[donor_id], recip_topics
            )
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


def main() -> None:
    logger = setup_stdout_logger("setup_citadel", LOG_LEVEL)
    try:
        asyncio.run(_run(logger))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
