"""
Прогоняет историю сообщений через пайплайн зеркалирования
для направлений, у которых задан past_mode.

Использование:
    python past_mode.py

Предупреждение: использует тот же SESSION_STRING, что и основной сервис.
Не запускайте одновременно с main.py.
"""

import asyncio
import logging
import sys
from pathlib import Path
from time import monotonic
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from config import (
        API_APP_VERSION,
        API_DEVICE_MODEL,
        API_HASH,
        API_ID,
        API_SYSTEM_VERSION,
        CHAT_MAPPING,
        DB_URL,
        DirectionConfig,
        LOG_LEVEL,
        SESSION_STRING,
        USE_MEMORY_DB,
    )
except Exception:
    print("Failed reading .env")
    raise

from telethon import TelegramClient, errors, utils
from telethon.sessions import StringSession

from telemirror._patch import patch_input_media_with_spoiler
from telemirror.mirroring import EventProcessor
from telemirror.storage import Database, InMemoryDatabase, PostgresDatabase


def _configure_logging(log_level: str) -> logging.Logger:
    logger = logging.getLogger("past_mode")
    logger.setLevel(log_level)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(
            logging.Formatter(
                "%(levelname)-5s %(asctime)s [%(filename)s:%(lineno)d]:%(name)s: %(message)s"
            )
        )
        logger.addHandler(handler)
    return logger


def _strategy_label(pm) -> str:
    if pm.since_date is not None:
        return f"since_date={pm.since_date.isoformat()}"
    if pm.last_n is not None:
        return f"last_n={pm.last_n}"
    return "full_history"


def _log_progress(
    logger: logging.Logger, prefix: str, processed: int, total: int, start_time: float
) -> None:
    elapsed = monotonic() - start_time
    if total > 0:
        pct = processed / total * 100.0
        eta = f", ETA {elapsed / processed * (total - processed):.0f}s" if processed else ""
        logger.info(f"{prefix}: {processed}/{total} ({pct:.1f}%){eta}")
    else:
        logger.info(f"{prefix}: обработано {processed}")


async def _replay_direction(
    client: TelegramClient,
    database: Database,
    source_id: int,
    target_id: int,
    cfg: DirectionConfig,
    logger: logging.Logger,
) -> None:
    pm = cfg.past_mode
    prefix = f"[PastMode] {source_id}→{target_id}"
    logger.info(f"{prefix}: старт (стратегия={_strategy_label(pm)})")

    checkpoint: Optional[int] = await database.get_past_mode_checkpoint(source_id, target_id)
    if checkpoint:
        logger.info(f"{prefix}: продолжение с message_id={checkpoint}")

    try:
        total = (await client.get_messages(source_id, limit=0)).total
    except Exception as e:
        logger.warning(f"{prefix}: не удалось получить total: {e}")
        total = 0

    # last_n без чекпоинта: собрать в память (новейшие первые), перевернуть
    use_buffer = pm.last_n is not None and checkpoint is None
    if use_buffer:
        buffer: List = []
        async for msg in client.iter_messages(source_id, limit=pm.last_n):
            buffer.append(msg)
        buffer.reverse()
        iter_total = len(buffer)
    else:
        iter_kwargs: dict = {"reverse": True}
        if checkpoint is not None:
            iter_kwargs["min_id"] = checkpoint  # min_id эксклюзивен — продолжаем со следующего
        elif pm.since_date is not None:
            iter_kwargs["offset_date"] = pm.since_date
        # full_history: только reverse=True
        iter_total = total

    # Один EventProcessor на направление — переиспользует существующую логику фильтров и отправки
    processor = EventProcessor(
        chat_mapping={source_id: {target_id: [cfg]}},
        database=database,
        client=client,
        logger=logger,
    )

    processed = 0
    start_time = monotonic()
    pending_album: List = []
    pending_gid: Optional[int] = None

    async def flush_album() -> None:
        nonlocal processed, pending_album, pending_gid
        if not pending_album:
            return
        first = pending_album[0]
        link = f"https://t.me/c/{utils.resolve_id(source_id)[0]}/{first.id}"
        await processor.new_album(source_id, pending_album, link)
        await database.set_past_mode_checkpoint(source_id, target_id, first.id)
        processed += 1
        _log_progress(logger, prefix, processed, iter_total, start_time)
        await asyncio.sleep(pm.send_delay)
        pending_album = []
        pending_gid = None

    async def process_single(msg) -> None:
        nonlocal processed
        link = f"https://t.me/c/{utils.resolve_id(source_id)[0]}/{msg.id}"
        await processor.new_message(source_id, msg, link)
        await database.set_past_mode_checkpoint(source_id, target_id, msg.id)
        processed += 1
        _log_progress(logger, prefix, processed, iter_total, start_time)
        await asyncio.sleep(pm.send_delay)

    async def handle_msg(msg) -> None:
        nonlocal pending_gid
        gid = getattr(msg, "grouped_id", None)
        if gid is not None:
            if gid != pending_gid:
                await flush_album()
                pending_gid = gid
            pending_album.append(msg)
        else:
            await flush_album()
            await process_single(msg)

    if use_buffer:
        for msg in buffer:
            await handle_msg(msg)
    else:
        async for msg in client.iter_messages(source_id, **iter_kwargs):
            await handle_msg(msg)

    await flush_album()

    logger.info(f"{prefix}: завершено. Обработано {processed} сообщений/альбомов.")


async def _run(logger: logging.Logger) -> None:
    logger.warning(
        "past_mode.py использует тот же SESSION_STRING, что и живой сервис. "
        "Убедитесь, что main.py НЕ запущен."
    )

    directions = [
        (src, tgt, cfg)
        for src, targets in CHAT_MAPPING.items()
        for tgt, cfgs in targets.items()
        for cfg in cfgs
        if cfg.past_mode is not None
    ]

    if not directions:
        logger.warning(
            "Нет направлений с past_mode. "
            "Добавьте past_mode: в конфиг (YAML) или PAST_MODE= в .env."
        )
        return

    logger.info(f"Найдено {len(directions)} направление(й) для воспроизведения.")

    database: Database = (
        InMemoryDatabase() if USE_MEMORY_DB else await PostgresDatabase(connection_string=DB_URL)
    )

    patch_input_media_with_spoiler()

    client = TelegramClient(
        StringSession(SESSION_STRING),
        API_ID,
        API_HASH,
        device_model=API_DEVICE_MODEL,
        system_version=API_SYSTEM_VERSION,
        app_version=API_APP_VERSION,
        flood_sleep_threshold=60,  # Telethon auto-sleep для FloodWait ≤60s
    )
    client.parse_mode = "markdown"
    await client.connect()

    me = await client.get_me()
    if me is None:
        raise RuntimeError("Нет авторизации. Запустите login.py для получения SESSION_STRING.")
    logger.info(f"Вошли как {utils.get_display_name(me)} ({me.phone})")

    try:
        for source_id, target_id, cfg in directions:
            try:
                await _replay_direction(client, database, source_id, target_id, cfg, logger)
            except errors.FloodWaitError as e:
                logger.warning(f"FloodWait {e.seconds}s при получении истории, ждём...")
                await asyncio.sleep(e.seconds)
    finally:
        await client.disconnect()


def main() -> None:
    logger = _configure_logging(LOG_LEVEL)
    asyncio.run(_run(logger))


if __name__ == "__main__":
    main()
