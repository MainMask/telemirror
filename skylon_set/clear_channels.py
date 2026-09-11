"""
Удаляет все сообщения во всех каналах-получателях и топиках супергрупп,
описанных в конфиге (CHAT_MAPPING).

Использование:
    python clear_channels.py           # с подтверждением
    python clear_channels.py --dry-run # только показывает цели

Предупреждение: использует тот же SESSION_STRING, что и основной сервис.
Не запускайте одновременно с main.py.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Dict, Optional, Set

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from config import CHAT_MAPPING, DB_URL, LOG_LEVEL, USE_MEMORY_DB
except Exception:
    print("Failed reading .env")
    raise

import psycopg
from telethon import TelegramClient, errors, utils
from telethon.tl.functions.channels import DeleteHistoryRequest

from skylon_set._common import configure_logging, make_client

GENERAL_TOPIC_ID = 1
DELETE_BATCH = 100


def _get_msg_topic(msg) -> int:
    """topic_id сообщения (та же логика, что EventProcessor._matches_from_topic)."""
    if msg.reply_to and msg.reply_to.forum_topic:
        return msg.reply_to.reply_to_top_id or msg.reply_to.reply_to_msg_id
    return GENERAL_TOPIC_ID


def collect_targets(chat_mapping) -> Dict[int, Set[Optional[int]]]:
    """Собирает {channel_id: set(topic_ids)} из целевых каналов CHAT_MAPPING."""
    targets: Dict[int, Set[Optional[int]]] = {}
    for _, tgt_map in chat_mapping.items():
        for tgt_id, cfgs in tgt_map.items():
            for cfg in cfgs:
                targets.setdefault(tgt_id, set()).add(cfg.to_topic_id)
    return targets


def channels_for_full_clear(targets: Dict[int, Set[Optional[int]]]) -> list:
    """Каналы, у которых нет топик-scoping — только их можно чистить целиком
    через DeleteHistory."""
    return [channel_id for channel_id, topic_ids in targets.items() if None in topic_ids]


async def purge(
    client: TelegramClient,
    channel_id: int,
    topic_id: Optional[int],
    dry_run: bool,
    logger: logging.Logger,
) -> int:
    """Удаляет сообщения в канале (или конкретном топике). Возвращает кол-во удалённых."""
    label = f"{channel_id}#{topic_id}" if topic_id is not None else str(channel_id)
    deleted = 0
    batch = []

    async def flush():
        nonlocal deleted
        if not batch:
            return
        if not dry_run:
            while True:
                try:
                    await client.delete_messages(channel_id, batch)
                    break
                except errors.FloodWaitError as e:
                    logger.warning(f"[{label}] FloodWait {e.seconds}s, ждём...")
                    await asyncio.sleep(e.seconds)
        deleted += len(batch)
        batch.clear()

    async for msg in client.iter_messages(channel_id):
        if msg.action is not None:  # MessageService (channel created, pin, etc.) — skip
            continue
        if topic_id is not None and _get_msg_topic(msg) != topic_id:
            continue
        batch.append(msg.id)
        if len(batch) >= DELETE_BATCH:
            await flush()

    await flush()

    action = "Найдено (dry-run)" if dry_run else "Удалено"
    logger.info(f"[{label}] {action}: {deleted} сообщений")
    return deleted


async def _reset_checkpoints(
    cleared_targets: Dict[int, Set[Optional[int]]],
    dry_run: bool,
    logger: logging.Logger,
) -> None:
    """Сбрасывает past_mode чекпоинты для очищенных целевых каналов."""
    pairs = [
        (src, tgt)
        for src, tgt_map in CHAT_MAPPING.items()
        for tgt in tgt_map
        if tgt in cleared_targets
    ]
    if not pairs:
        return

    if dry_run:
        logger.info(f"(dry-run) Было бы сброшено {len(pairs)} чекпоинт(ов): {pairs}")
        return

    if USE_MEMORY_DB:
        return  # in-memory чекпоинты не переживают перезапуск

    async with await psycopg.AsyncConnection.connect(DB_URL) as conn:
        async with conn.cursor() as cur:
            for src, tgt in pairs:
                await cur.execute(
                    "DELETE FROM past_mode_checkpoint "
                    "WHERE source_channel = %s AND target_channel = %s",
                    (src, tgt),
                )
                logger.info(f"[checkpoint] сброшен: {src}→{tgt}")


async def _clear_bindings(
    cleared_targets: Dict[int, Set[Optional[int]]],
    dry_run: bool,
    logger: logging.Logger,
) -> None:
    """Удаляет записи binding_id для очищенных целевых каналов."""
    target_ids = list(cleared_targets.keys())
    if not target_ids:
        return

    if dry_run:
        logger.info(f"(dry-run) Было бы очищено binding_id для {len(target_ids)} канала(ов): {target_ids}")
        return

    if USE_MEMORY_DB:
        return

    async with await psycopg.AsyncConnection.connect(DB_URL) as conn:
        async with conn.cursor() as cur:
            for tgt in target_ids:
                await cur.execute(
                    "DELETE FROM binding_id WHERE mirror_channel = %s",
                    (tgt,),
                )
                logger.info(f"[binding_id] очищен: {tgt}")


async def _run(logger: logging.Logger, dry_run: bool) -> None:
    logger.warning(
        "clear_channels.py использует тот же SESSION_STRING, что и живой сервис. "
        "Убедитесь, что main.py НЕ запущен."
    )

    targets = collect_targets(CHAT_MAPPING)
    if not targets:
        logger.warning("CHAT_MAPPING пуст — нечего очищать.")
        return

    # Строим список задач: если None в topic_ids — чистим весь канал (одна задача без фильтра)
    tasks = []
    for channel_id, topic_ids in targets.items():
        if None in topic_ids:
            tasks.append((channel_id, None))
        else:
            for topic_id in sorted(topic_ids):
                tasks.append((channel_id, topic_id))

    logger.info(f"Целей для очистки: {len(tasks)}")
    for channel_id, topic_id in tasks:
        label = f"{channel_id}#{topic_id}" if topic_id is not None else str(channel_id)
        logger.info(f"  {label}")

    if not dry_run:
        answer = input("\nПродолжить удаление? [y/N] ").strip().lower()
        if answer != "y":
            logger.info("Отменено.")
            return

    client = make_client(flood_sleep_threshold=60)
    client.parse_mode = "markdown"
    await client.connect()

    me = await client.get_me()
    if me is None:
        raise RuntimeError("Нет авторизации. Запустите login.py для получения SESSION_STRING.")
    at_username = f" (@{me.username})" if getattr(me, "username", None) else ""
    logger.info(f"Вошли как {utils.get_display_name(me)}{at_username}")

    total = 0
    try:
        for channel_id, topic_id in tasks:
            try:
                total += await purge(client, channel_id, topic_id, dry_run, logger)
            except Exception as e:
                label = f"{channel_id}#{topic_id}" if topic_id is not None else str(channel_id)
                logger.error(f"[{label}] Ошибка: {e}")

        # DeleteHistory очищает канал целиком — вызываем только для каналов без
        # топик-scoping в конфиге; для остальных историю уже почистил per-topic purge.
        full_clear_channels = channels_for_full_clear(targets)
        if dry_run:
            logger.info(
                f"(dry-run) Было бы вызвано DeleteHistory для {len(full_clear_channels)} "
                f"канала(ов) без топик-scoping"
            )
        else:
            for channel_id in full_clear_channels:
                try:
                    await client(DeleteHistoryRequest(channel=channel_id, max_id=0, for_everyone=True))
                    logger.info(f"[{channel_id}] DeleteHistory выполнен")
                except Exception as e:
                    logger.error(f"[{channel_id}] DeleteHistory ошибка: {e}")

        await _reset_checkpoints(targets, dry_run, logger)
        await _clear_bindings(targets, dry_run, logger)
    finally:
        await client.disconnect()

    action = "Найдено (dry-run)" if dry_run else "Итого удалено"
    logger.info(f"{action}: {total} сообщений во всех каналах.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Очистка каналов-получателей telemirror")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Только показать что будет удалено, без реального удаления",
    )
    args = parser.parse_args()

    logger = configure_logging("purge_targets", LOG_LEVEL)
    try:
        asyncio.run(_run(logger, args.dry_run))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
