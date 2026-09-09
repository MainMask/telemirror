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

from telethon import TelegramClient
from telethon.tl.functions.channels import DeleteHistoryRequest

from telemirror.misc.log_setup import setup_stdout_logger
from telemirror.misc.topics import topic_id_of
from telemirror.storage import PostgresDatabase
from skylon_set._common import open_client, safe_call

DELETE_BATCH = 100


def collect_targets(chat_mapping) -> Dict[int, Set[Optional[int]]]:
    """Собирает {channel_id: set(topic_ids)} из целевых каналов CHAT_MAPPING."""
    targets: Dict[int, Set[Optional[int]]] = {}
    for tgt_map in chat_mapping.values():
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
    topic_ids: Set[int],
    dry_run: bool,
    logger: logging.Logger,
) -> int:
    """Удаляет сообщения указанных топиков канала за один проход по истории.

    Раньше вызывалась по разу на каждый топик — K полных проходов по истории
    канала; теперь один проход маршрутизирует сообщения по нужным топикам.
    """
    label = f"{channel_id} топики {sorted(topic_ids)}"
    deleted = 0
    batch: list = []

    async def flush():
        nonlocal deleted
        if not batch:
            return
        if not dry_run:
            await safe_call(
                client,
                lambda ids=list(batch): client.delete_messages(channel_id, ids),
            )
        deleted += len(batch)
        batch.clear()

    async for msg in client.iter_messages(channel_id):
        if msg.action is not None:  # MessageService (channel created, pin, etc.) — skip
            continue
        if topic_id_of(msg) not in topic_ids:
            continue
        batch.append(msg.id)
        if len(batch) >= DELETE_BATCH:
            await flush()

    await flush()

    action = "Найдено (dry-run)" if dry_run else "Удалено"
    logger.info(f"[{label}] {action}: {deleted} сообщений")
    return deleted


async def _reset_db_state(
    cleared_targets: Dict[int, Set[Optional[int]]],
    dry_run: bool,
    logger: logging.Logger,
) -> None:
    """Сбрасывает past_mode чекпоинты и записи binding_id очищенных целевых каналов."""
    pairs = [
        (src, tgt)
        for src, tgt_map in CHAT_MAPPING.items()
        for tgt in tgt_map
        if tgt in cleared_targets
    ]
    target_ids = list(cleared_targets)

    if dry_run:
        logger.info(
            f"(dry-run) Было бы сброшено {len(pairs)} чекпоинт(ов) и очищен "
            f"binding_id для {len(target_ids)} канала(ов)"
        )
        return

    if USE_MEMORY_DB:
        return  # in-memory состояние не переживает перезапуск

    db = await PostgresDatabase(connection_string=DB_URL)
    try:
        for src, tgt in pairs:
            await db.delete_past_mode_checkpoint(src, tgt)
            logger.info(f"[checkpoint] сброшен: {src}→{tgt}")
        for tgt in target_ids:
            await db.delete_bindings_for_mirror(tgt)
            logger.info(f"[binding_id] очищен: {tgt}")
    finally:
        await db.close()


async def _run(logger: logging.Logger, dry_run: bool) -> None:
    logger.warning(
        "clear_channels.py использует тот же SESSION_STRING, что и живой сервис. "
        "Убедитесь, что main.py НЕ запущен."
    )

    targets = collect_targets(CHAT_MAPPING)
    if not targets:
        logger.warning("CHAT_MAPPING пуст — нечего очищать.")
        return

    # Каналы без топик-scoping чистит DeleteHistory целиком — по истории их не
    # сканируем. Остальные — один проход на канал по множеству их топиков.
    full_clear = set(channels_for_full_clear(targets))
    topic_only = {
        channel_id: {t for t in topic_ids if t is not None}
        for channel_id, topic_ids in targets.items()
        if channel_id not in full_clear
    }

    logger.info(
        f"Целей: {len(topic_only)} топик-scoped + {len(full_clear)} полная очистка"
    )
    for channel_id, tids in topic_only.items():
        logger.info(f"  {channel_id} топики {sorted(tids)}")
    for channel_id in full_clear:
        logger.info(f"  {channel_id} (DeleteHistory)")

    if not dry_run:
        answer = input("\nПродолжить удаление? [y/N] ").strip().lower()
        if answer != "y":
            logger.info("Отменено.")
            return

    total = 0
    async with open_client(
        logger, warn_main_running=False, flood_sleep_threshold=60
    ) as (client, _me):
        for channel_id, tids in topic_only.items():
            try:
                total += await purge(client, channel_id, tids, dry_run, logger)
            except Exception as e:
                logger.error(f"[{channel_id}] Ошибка: {e}")

        if dry_run:
            logger.info(
                f"(dry-run) Было бы вызвано DeleteHistory для {len(full_clear)} канала(ов)"
            )
        else:
            for channel_id in full_clear:
                try:
                    await client(DeleteHistoryRequest(
                        channel=channel_id, max_id=0, for_everyone=True
                    ))
                    logger.info(f"[{channel_id}] DeleteHistory выполнен")
                except Exception as e:
                    logger.error(f"[{channel_id}] DeleteHistory ошибка: {e}")

        await _reset_db_state(targets, dry_run, logger)

    action = "Найдено (dry-run)" if dry_run else "Итого удалено"
    logger.info(f"{action}: {total} сообщений (топик-scoped каналы).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Очистка каналов-получателей telemirror")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Только показать что будет удалено, без реального удаления",
    )
    args = parser.parse_args()

    logger = setup_stdout_logger("purge_targets", LOG_LEVEL)
    try:
        asyncio.run(_run(logger, args.dry_run))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
