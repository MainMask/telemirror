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
from copy import deepcopy
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
        TECH_CHANNEL,
        USE_MEMORY_DB,
    )
except Exception:
    print("Failed reading .env")
    raise

from telethon import TelegramClient, errors, utils
from telethon.sessions import StringSession
from telethon.tl import types

from telemirror._patch import patch_input_media_with_spoiler
from telemirror.mirroring import EventProcessor
from telemirror.storage import Database, InMemoryDatabase, PostgresDatabase

_LOG_EVERY = 25  # логировать прогресс каждые N сообщений/альбомов


def _configure_logging(log_level: str) -> logging.Logger:
    formatter = logging.Formatter(
        "%(levelname)-5s %(asctime)s [%(filename)s:%(lineno)d]:%(name)s: %(message)s"
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(formatter)

    logger = logging.getLogger("past_mode")
    logger.setLevel(log_level)
    if not logger.handlers:
        logger.addHandler(handler)

    # Telethon's reconnection messages go through its own logger — attach our handler
    # so they appear with timestamps alongside our progress logs.
    telethon_logger = logging.getLogger("telethon")
    telethon_logger.setLevel(logging.WARNING)
    if not telethon_logger.handlers:
        telethon_logger.addHandler(handler)

    return logger


def _strategy_label(pm) -> str:
    if pm.since_date is not None:
        return f"since_date={pm.since_date.isoformat()}"
    if pm.last_n is not None:
        return f"last_n={pm.last_n}"
    return "full_history"


def _format_duration(seconds: float) -> str:
    if seconds >= 3600:
        return f"{seconds / 3600:.1f}ч"
    if seconds >= 60:
        return f"{seconds / 60:.0f}мин"
    return f"{seconds:.0f}с"


def _log_progress(
    logger: logging.Logger, prefix: str, processed: int, total: int, start_time: float
) -> None:
    elapsed = monotonic() - start_time
    if total > 0:
        pct = processed / total * 100.0
        eta = f", ETA {elapsed / processed * (total - processed):.0f}s" if processed >= 3 else ""
        logger.info(f"{prefix}: {processed}/{total} ({pct:.1f}%){eta}")
    else:
        logger.info(f"{prefix}: обработано {processed}")


async def _integrity_check(
    database: Database,
    source_id: int,
    target_id: int,
    logger: logging.Logger,
) -> tuple[Optional[int], int]:
    """Проверяет чекпоинт, возвращает (скорректированный checkpoint, кол-во зеркал в БД)."""
    prefix = f"[PastMode] {source_id}→{target_id}"
    checkpoint = await database.get_past_mode_checkpoint(source_id, target_id)
    if checkpoint is None:
        return None, 0

    mirrors = await database.get_messages_for_channel_pair(source_id, target_id)
    mirror_count = len(mirrors)
    logger.info(f"{prefix}: чекпоинт={checkpoint}, зеркал в БД={mirror_count}")

    if mirror_count == 0:
        logger.warning(
            f"{prefix}: чекпоинт={checkpoint} есть, но зеркала не найдены "
            "(возможно, все сообщения отфильтрованы или проблема с БД)"
        )
        return checkpoint, 0

    max_mirrored = max(m.original_id for m in mirrors)
    if checkpoint < max_mirrored:
        logger.warning(
            f"{prefix}: checkpoint={checkpoint} < max_mirrored={max_mirrored}, "
            f"откат checkpoint до {max_mirrored}"
        )
        await database.set_past_mode_checkpoint(source_id, target_id, max_mirrored)
        return max_mirrored, mirror_count

    return checkpoint, mirror_count


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

    checkpoint, mirrors_done = await _integrity_check(database, source_id, target_id, logger)
    if checkpoint is not None:
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
        iter_total = (
            max(0, pm.last_n - mirrors_done)
            if pm.last_n is not None and checkpoint is not None
            else total
        )

    if iter_total > 0:
        eta_str = (
            f", не менее ≈{_format_duration(iter_total * pm.send_delay)} (только send_delay, без учёта загрузки)"
            if pm.send_delay > 0
            else ""
        )
        logger.info(f"{prefix}: ~{iter_total} сообщений к обработке{eta_str}")

    # Full CHAT_MAPPING is needed so _try_rewrite_tg_link can resolve cross-channel links.
    # Override only the current source to this single direction to keep routing correct.
    processor = EventProcessor(
        chat_mapping={**CHAT_MAPPING, source_id: {target_id: [cfg]}},
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
        await database.set_past_mode_checkpoint(source_id, target_id, pending_album[-1].id)
        processed += 1
        if processed == 1 or processed % _LOG_EVERY == 0:
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
        if processed == 1 or processed % _LOG_EVERY == 0:
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


async def _edit_links_pass(
    client: TelegramClient,
    database: Database,
    directions: List,
    logger: logging.Logger,
) -> None:
    """Второй проход: исправляет перекрёстные ссылки в уже отправленных сообщениях."""
    for source_id, target_id, cfg in directions:
        if cfg.mode != "copy":
            continue

        prefix = f"[EditPass] {source_id}→{target_id}"
        mirrors = await database.get_messages_for_channel_pair(source_id, target_id)
        if not mirrors:
            continue

        processor = EventProcessor(
            chat_mapping={**CHAT_MAPPING, source_id: {target_id: [cfg]}},
            database=database,
            client=client,
            logger=logger,
        )

        mirror_map = {m.original_id: m for m in mirrors}
        try:
            _ids = list(mirror_map.keys())
            _BATCH = 100
            src_messages = []
            for _i in range(0, len(_ids), _BATCH):
                src_messages.extend(
                    await client.get_messages(source_id, ids=_ids[_i : _i + _BATCH])
                )
        except Exception as e:
            logger.warning(f"{prefix}: не удалось получить сообщения batch: {e}")
            continue

        edited = 0
        for src_msg in src_messages:
            if not src_msg or not src_msg.entities:
                continue
            if not any(
                isinstance(e, (types.MessageEntityTextUrl, types.MessageEntityUrl))
                for e in src_msg.entities
            ):
                continue

            mirror = mirror_map[src_msg.id]
            msg_copy = processor.copy_message(src_msg)
            entities_before = deepcopy(msg_copy.entities)
            text_before = msg_copy.message
            await processor._rewrite_links(msg_copy, source_id, cfg.fallback_link_url)

            text_changed = msg_copy.message != text_before
            url_changed = any(
                getattr(a, "url", None) != getattr(b, "url", None)
                for a, b in zip(msg_copy.entities or [], entities_before or [])
            )
            if not text_changed and not url_changed:
                continue

            try:
                await client.edit_message(
                    entity=target_id,
                    message=mirror.mirror_id,
                    text=msg_copy.message,
                    formatting_entities=msg_copy.entities,
                )
                edited += 1
                logger.info(f"{prefix}: исправлена ссылка в {mirror.original_id}→{mirror.mirror_id}")
                if cfg.past_mode.send_delay:
                    await asyncio.sleep(cfg.past_mode.send_delay)
            except Exception as e:
                logger.warning(
                    f"{prefix}: ошибка редактирования {mirror.mirror_id}: "
                    f"{type(e).__name__}: {e}"
                )

        if edited:
            logger.info(f"{prefix}: исправлено {edited} сообщени(ий)")


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

    _CONN_RETRIES = 20
    _RETRY_DELAY = 3  # секунд между попытками переподключения

    client = TelegramClient(
        StringSession(SESSION_STRING),
        API_ID,
        API_HASH,
        device_model=API_DEVICE_MODEL,
        system_version=API_SYSTEM_VERSION,
        app_version=API_APP_VERSION,
        flood_sleep_threshold=300,  # Telethon auto-sleep для FloodWait ≤300s (как в main.py)
        connection_retries=_CONN_RETRIES,
        retry_delay=_RETRY_DELAY,
    )
    logger.info(
        f"При обрыве соединения: до {_CONN_RETRIES} попыток с задержкой {_RETRY_DELAY}s между ними"
    )
    client.parse_mode = "markdown"
    await client.connect()

    me = await client.get_me()
    if me is None:
        raise RuntimeError("Нет авторизации. Запустите login.py для получения SESSION_STRING.")
    _handle = f" (@{me.username})" if getattr(me, "username", None) else ""
    logger.info(f"Вошли как {utils.get_display_name(me)}{_handle}")

    try:
        for source_id, target_id, cfg in directions:
            while True:
                try:
                    await _replay_direction(client, database, source_id, target_id, cfg, logger)
                    break
                except errors.FloodWaitError as e:
                    # Telethon auto-sleeps for FloodWait ≤300s (flood_sleep_threshold).
                    # This branch fires only for >300s waits during iter_messages.
                    # Checkpoint is saved, so after sleeping we retry from where we left off.
                    logger.warning(f"FloodWait {e.seconds}s при получении истории, ждём и повторяем...")
                    await asyncio.sleep(e.seconds)

        # Second pass: fix cross-channel links that couldn't be resolved during mirroring
        logger.info("Второй проход: исправление перекрёстных ссылок...")
        await _edit_links_pass(client, database, directions, logger)

        if TECH_CHANNEL:
            pairs = "\n".join(f"• `{s}` → `{t}`" for s, t, _ in directions)
            header = f"✅ Past mode завершён. Скопирована история {len(directions)} направлени(й)."
            full = f"{header}\n\n{pairs}"
            await client.send_message(TECH_CHANNEL, full if len(full) <= 4096 else header)
    finally:
        await client.disconnect()
        if hasattr(database, "connection_pool"):
            await database.connection_pool.close()


def main() -> None:
    logger = _configure_logging(LOG_LEVEL)
    asyncio.run(_run(logger))


if __name__ == "__main__":
    main()
