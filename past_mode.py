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
from typing import Dict, List, Optional, Tuple

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

from telemirror.mirroring import EventProcessor
from telemirror.misc.links import private_message_link
from telemirror.misc.log_setup import setup_stdout_logger
from telemirror.misc.message_groups import iter_message_groups
from telemirror.storage import Database, InMemoryDatabase, PostgresDatabase

_LOG_EVERY = 25  # логировать прогресс каждые N сообщений/альбомов


def _configure_logging(log_level: str) -> logging.Logger:
    logger = setup_stdout_logger("past_mode", log_level)
    # Telethon's reconnection messages go through its own logger — give it the
    # same stdout format so they appear with timestamps alongside our progress logs.
    setup_stdout_logger("telethon", logging.WARNING)
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


def _log_overall(
    logger: logging.Logger,
    pair_no: int,
    pair_count: int,
    done: int,
    total: int,
    run_start: float,
) -> None:
    """Сквозная строка прогресса по всем парам каналов."""
    elapsed = monotonic() - run_start
    if total > 0 and done > 0:
        pct = min(100.0, done / total * 100.0)
        eta = (
            f" • ETA ~{_format_duration(elapsed / done * (total - done))}"
            if done < total
            else ""
        )
        tail = f"суммарно ~{done}/{total} ({pct:.0f}%){eta}"
    else:
        tail = f"суммарно обработано {done}"
    logger.info(
        f"[Прогресс] пара {pair_no}/{pair_count} • {tail} • прошло {_format_duration(elapsed)}"
    )


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
            f"сдвигаю checkpoint вперёд до {max_mirrored} "
            f"(сообщения между {checkpoint} и {max_mirrored} без зеркал при resume пропускаются)"
        )
        await database.set_past_mode_checkpoint(source_id, target_id, max_mirrored)
        return max_mirrored, mirror_count

    return checkpoint, mirror_count


async def _replay_direction(
    client: TelegramClient,
    database: Database,
    source_id: int,
    target_id: int,
    cfgs: List[DirectionConfig],
    logger: logging.Logger,
    total: Optional[int] = None,
) -> int:
    """Один проход по истории канала на пару (source, target).

    Все топик-направления пары обрабатываются за этот проход: процессор
    маршрутизирует каждое сообщение по тем cfg, чей from_topic_id совпадает.
    `total` (кол-во сообщений источника) переиспользуется из _run, если передан.
    Возвращает число обработанных сообщений/альбомов.
    """
    pm = cfgs[0].past_mode
    prefix = f"[PastMode] {source_id}→{target_id}"

    labels = {_strategy_label(c.past_mode) for c in cfgs}
    if len(labels) > 1:
        logger.warning(
            f"{prefix}: у топиков пары разные стратегии past_mode ({sorted(labels)}), "
            f"беру первую ({_strategy_label(pm)})"
        )
    topics_note = "" if len(cfgs) == 1 else f", топиков={len(cfgs)}"
    logger.info(f"{prefix}: старт (стратегия={_strategy_label(pm)}{topics_note})")

    checkpoint, mirrors_done = await _integrity_check(database, source_id, target_id, logger)
    if checkpoint is not None:
        logger.info(f"{prefix}: продолжение с message_id={checkpoint}")

    if total is None:
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
    # Override only the current source to this single target pair to keep routing correct.
    processor = EventProcessor(
        chat_mapping={**CHAT_MAPPING, source_id: {target_id: cfgs}},
        database=database,
        client=client,
        logger=logger,
    )

    processed = 0
    start_time = monotonic()

    def _log_step() -> None:
        if processed == 1 or processed % _LOG_EVERY == 0:
            _log_progress(logger, prefix, processed, iter_total, start_time)

    async def process_single(msg) -> None:
        nonlocal processed
        link = private_message_link(source_id, msg.id)
        await processor.new_message(source_id, msg, link)
        await database.set_past_mode_checkpoint(source_id, target_id, msg.id)
        processed += 1
        _log_step()
        await asyncio.sleep(pm.send_delay)

    async def process_album(album: List) -> None:
        nonlocal processed
        link = private_message_link(source_id, album[0].id)
        await processor.new_album(source_id, album, link)
        await database.set_past_mode_checkpoint(source_id, target_id, album[-1].id)
        processed += 1
        _log_step()
        await asyncio.sleep(pm.send_delay)

    async def _aiter(seq):
        for item in seq:
            yield item

    source = (
        _aiter(buffer)
        if use_buffer
        else client.iter_messages(source_id, **iter_kwargs)
    )
    # iter_message_groups drops non-Message items (service messages): they produce
    # no mirror, so they no longer advance the checkpoint (same as _sync_broadcast_channel).
    async for group in iter_message_groups(source):
        if isinstance(group, list):
            await process_album(group)
        else:
            await process_single(group)

    logger.info(f"{prefix}: завершено. Обработано {processed} сообщений/альбомов.")
    return processed


async def _replay_with_retry(
    client: TelegramClient,
    database: Database,
    source_id: int,
    target_id: int,
    cfgs: List[DirectionConfig],
    logger: logging.Logger,
    total: Optional[int] = None,
) -> int:
    """Run `_replay_direction`, retrying on a >threshold FloodWait.

    Telethon auto-sleeps for waits ≤300s (flood_sleep_threshold); this loop
    handles the larger ones — raised either from iter_messages or from a send
    (mirroring re-raises both flood types). The checkpoint is saved as we go,
    so after sleeping we resume from where we left off.
    """
    while True:
        try:
            return await _replay_direction(
                client, database, source_id, target_id, cfgs, logger, total
            )
        except (errors.FloodWaitError, errors.FloodPremiumWaitError) as e:
            logger.warning(f"FloodWait {e.seconds}s, ждём и повторяем...")
            await asyncio.sleep(e.seconds)


async def _edit_links_pass(
    client: TelegramClient,
    database: Database,
    pairs: Dict[Tuple[int, int], List[DirectionConfig]],
    logger: logging.Logger,
) -> None:
    """Второй проход: исправляет перекрёстные ссылки в уже отправленных сообщениях."""
    for (source_id, target_id), cfgs in pairs.items():
        # Работа тут пар-широкая (binding_id по паре каналов); берём первый
        # copy-топик пары — fallback_link_url/send_delay у топиков пары совпадают.
        cfg = next((c for c in cfgs if c.mode == "copy"), None)
        if cfg is None:
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
        _ids = list(mirror_map.keys())
        _BATCH = 100
        edited = 0
        # Stream the source messages batch by batch — for a full_history replay
        # `mirrors` can be tens of thousands, and accumulating every Message
        # object here just to iterate it once was a needless memory spike.
        for _i in range(0, len(_ids), _BATCH):
            try:
                src_batch = await client.get_messages(
                    source_id, ids=_ids[_i : _i + _BATCH]
                )
            except Exception as e:
                logger.warning(f"{prefix}: не удалось получить сообщения batch: {e}")
                break

            for src_msg in src_batch:
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
                await processor._rewrite_links(
                    msg_copy, source_id, cfg.fallback_link_url
                )

                text_changed = msg_copy.message != text_before
                url_changed = any(
                    getattr(a, "url", None) != getattr(b, "url", None)
                    for a, b in zip(
                        msg_copy.entities or [], entities_before or [], strict=False
                    )
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

    # Группируем по паре каналов: все топик-направления пары идут одним проходом.
    pairs: Dict[Tuple[int, int], List[DirectionConfig]] = {}
    for src, targets in CHAT_MAPPING.items():
        for tgt, cfgs in targets.items():
            pm_cfgs = [c for c in cfgs if c.past_mode is not None]
            if pm_cfgs:
                pairs[(src, tgt)] = pm_cfgs

    if not pairs:
        logger.warning(
            "Нет направлений с past_mode. "
            "Добавьте past_mode: в конфиг (YAML) или PAST_MODE= в .env."
        )
        return

    direction_count = sum(len(c) for c in pairs.values())
    logger.info(
        f"Найдено {direction_count} направление(й) в {len(pairs)} паре(ах) каналов "
        "для воспроизведения."
    )

    database: Database = (
        InMemoryDatabase() if USE_MEMORY_DB else await PostgresDatabase(connection_string=DB_URL)
    )

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
    at_username = f" (@{me.username})" if getattr(me, "username", None) else ""
    logger.info(f"Вошли как {utils.get_display_name(me)}{at_username}")

    try:
        # Общий прогресс: суммарный total по источникам как знаменатель
        # (один полный проход по каналу на пару, поэтому источник с N парами
        # учитывается N раз).
        source_total: Dict[int, int] = {}
        for src, _ in pairs:
            if src not in source_total:
                try:
                    source_total[src] = (await client.get_messages(src, limit=0)).total
                except Exception as e:
                    logger.warning(f"Не удалось получить total для {src}: {e}")
                    source_total[src] = 0
        overall_total = sum(source_total[src] for src, _ in pairs)
        overall_done = 0
        run_start = monotonic()

        for pair_no, ((source_id, target_id), cfgs) in enumerate(pairs.items(), start=1):
            overall_done += await _replay_with_retry(
                client, database, source_id, target_id, cfgs, logger,
                total=source_total[source_id],
            )
            _log_overall(
                logger, pair_no, len(pairs), overall_done, overall_total, run_start
            )

        # Second pass: fix cross-channel links that couldn't be resolved during mirroring
        logger.info("Второй проход: исправление перекрёстных ссылок...")
        await _edit_links_pass(client, database, pairs, logger)

        if TECH_CHANNEL:
            pair_lines = "\n".join(f"• `{s}` → `{t}`" for s, t in pairs)
            header = (
                f"✅ Past mode завершён. Скопирована история {len(pairs)} пар(ы) каналов "
                f"({direction_count} направлени(й))."
            )
            full = f"{header}\n\n{pair_lines}"
            await client.send_message(TECH_CHANNEL, full if len(full) <= 4096 else header)
    finally:
        await client.disconnect()
        await database.close()


def main() -> None:
    logger = _configure_logging(LOG_LEVEL)
    asyncio.run(_run(logger))


if __name__ == "__main__":
    main()
