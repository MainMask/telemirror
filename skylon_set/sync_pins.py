"""Переносит закреплённые сообщения каналов/супергрупп-доноров на соответствующие
зеркала у получателей.

Связка «id закрепа донора → id зеркала» берётся из таблицы ``binding_id``, которую
наполняет ``past_mode.py`` (нужна постоянная Postgres-БД). Закреп зеркала,
лежащего в топике форума, Telegram делает внутри этого топика автоматически —
маппинг топиков здесь не нужен.

По умолчанию режим reconcile: то, что донор открепил, открепляется и у получателя,
но только среди сообщений, созданных самим миррором (``managed_ids``). Ручные
закрепы пользователя (без строки в ``binding_id``) не трогаются. ``--additive``
отключает откреп.

Порядок закрепов донора точно воспроизводится только на чистом первом прогоне
(инкрементальный diff не переупорядочивает уже существующие закрепы).

Использование (при ОСТАНОВЛЕННОМ main.py — общий SESSION_STRING):
    python -m skylon_set.sync_pins --dry-run
    python -m skylon_set.sync_pins --only -1003007946025
    python -m skylon_set.sync_pins            # боевой прогон по всем парам

На большом форуме первый прогон может упереться в FloodWait при закреплении —
``safe_call`` их пережидает, прогон может занять несколько минут.
"""

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from config import BROADCAST_CHANNEL, CHAT_MAPPING, DB_URL, LOG_LEVEL, USE_MEMORY_DB
except Exception:
    print("Failed reading .env")
    raise

from telethon import errors
from telethon.tl import types
from telethon.tl.functions.messages import SearchRequest, UpdatePinnedMessageRequest
from telethon.tl.types import InputMessagesFilterPinned

from telemirror.misc.links import private_message_link
from telemirror.misc.log_setup import setup_stdout_logger
from telemirror.storage import MirrorMessage, PostgresDatabase
from skylon_set._common import open_client, safe_call


# ── Значения ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SyncPair:
    donor_id: int
    recipient_id: int
    topic_map: Dict[int, int]  # from_topic_id → to_topic_id ({} для канал-пары)

    @property
    def from_topics(self) -> List[int]:
        return sorted(self.topic_map)

    @property
    def to_topics(self) -> List[int]:
        return sorted(set(self.topic_map.values()))


@dataclass(frozen=True)
class PinPlan:
    to_pin: List[int]    # mirror id, порядок: старые → новые
    to_unpin: List[int]  # mirror id


@dataclass
class PairSummary:
    donor_id: int
    recipient_id: int
    desired: int = 0
    already_pinned: int = 0
    pinned: int = 0
    unpinned: int = 0
    skipped_no_binding: int = 0
    dupes: List[int] = field(default_factory=list)


# ── Чистые функции ───────────────────────────────────────────────────────────

def iter_sync_directions(
    chat_mapping: Dict[int, Dict[int, list]],
    broadcast_channel: Optional[int],
    include_broadcast: bool = False,
) -> List[SyncPair]:
    """CHAT_MAPPING → список пар донор→получатель.

    Пара, где ДОНОР — это broadcast-канал, пропускается (если не include_broadcast):
    его посты веерятся во все цели, и переносить админский закреп в 8 чужих каналов
    обычно не нужно. Быть broadcast-ПОЛУЧАТЕЛЕМ — не повод исключать пару.
    """
    pairs: List[SyncPair] = []
    for donor_id, tgt_map in chat_mapping.items():
        if donor_id == broadcast_channel and not include_broadcast:
            continue
        for recipient_id, cfgs in tgt_map.items():
            topic_map = {
                c.from_topic_id: c.to_topic_id
                for c in cfgs
                if c.from_topic_id is not None
            }
            pairs.append(
                SyncPair(
                    donor_id=donor_id,
                    recipient_id=recipient_id,
                    topic_map=topic_map,
                )
            )
    return pairs


def build_pin_map(
    rows: List[MirrorMessage],
) -> Tuple[Dict[int, int], List[int]]:
    """rows из get_messages_for_channel_pair → ({original_id: mirror_id}, [дубли]).

    При нескольких разных mirror_id на один original_id берётся наименьший
    (детерминизм), original_id попадает в список дублей.
    """
    grouped: Dict[int, Set[int]] = {}
    for r in rows:
        grouped.setdefault(r.original_id, set()).add(r.mirror_id)
    pin_map = {oid: min(mids) for oid, mids in grouped.items()}
    dupes = sorted(oid for oid, mids in grouped.items() if len(mids) > 1)
    return pin_map, dupes


def resolve_desired_pins(
    donor_pins: Sequence["types.Message"],
    pin_map: Dict[int, int],
    logger: logging.Logger,
    label: str,
) -> Tuple[List[int], int]:
    """Закрепы донора → список mirror_id (в порядке donor_pins).

    Закрепы без строки в binding_id (сообщение отброшено фильтром при
    зеркалировании / служебное / старше past_mode) пропускаются.
    Возвращает (mirror_ids, skipped_no_binding).
    """
    desired: List[int] = []
    skipped = 0
    for msg in donor_pins:
        mirror_id = pin_map.get(msg.id)
        if mirror_id is None:
            skipped += 1
            logger.info(
                f"[{label}] закреп донора без зеркала, пропуск: "
                f"{private_message_link(msg.chat_id, msg.id)}"
            )
            continue
        desired.append(mirror_id)
    return desired, skipped


def plan_pin_actions(
    desired: Sequence[int],
    current_pinned_ids: Set[int],
    managed_ids: Set[int],
    *,
    reconcile: bool,
    allow_clear: bool = False,
) -> PinPlan:
    desired_set = set(desired)
    to_pin = sorted(desired_set - current_pinned_ids)  # по возрастанию ≈ старые первыми
    if not reconcile:
        return PinPlan(to_pin, [])
    stale = (current_pinned_ids & managed_ids) - desired_set
    if not desired_set and stale and not allow_clear:
        # У донора внезапно ноль закрепов — вероятнее сбой загрузки, чем реальный
        # массовый откреп. Не трогаем, пока не передан --allow-clear.
        return PinPlan(to_pin, [])
    return PinPlan(to_pin, sorted(stale))


# ── I/O ──────────────────────────────────────────────────────────────────────

async def fetch_pinned(
    client,
    peer: int,
    topic_ids: Optional[Sequence[int]],
    max_pins: int,
    thorough: bool,
    logger: logging.Logger,
) -> List["types.Message"]:
    """Закреплённые сообщения peer'а: общий проход по всему чату + (при --thorough)
    точечно по каждому топику. Объединение по id.
    """
    by_id: Dict[int, "types.Message"] = {}

    whole = await safe_call(
        client,
        lambda: client.get_messages(
            peer, filter=InputMessagesFilterPinned(), limit=None
        ),
    )
    if whole is None:
        logger.warning(f"[{peer}] нет доступа к закрепам, пропуск")
        return []
    for m in whole:
        by_id[m.id] = m

    if thorough and topic_ids:
        for tid in topic_ids:
            res = await safe_call(
                client,
                lambda t=tid: client(
                    SearchRequest(
                        peer=peer,
                        q="",
                        filter=InputMessagesFilterPinned(),
                        min_date=None,
                        max_date=None,
                        offset_id=0,
                        add_offset=0,
                        limit=max_pins,
                        max_id=0,
                        min_id=0,
                        hash=0,
                        top_msg_id=t,
                    )
                ),
            )
            if res is None:
                continue
            if len(res.messages) == max_pins:
                logger.warning(
                    f"[{peer}#{tid}] вернулось ровно {max_pins} закрепов — "
                    f"возможна обрезка, увеличьте --max-pins"
                )
            for m in res.messages:
                by_id.setdefault(m.id, m)

    return list(by_id.values())


async def sync_pair(
    client,
    db: PostgresDatabase,
    pair: SyncPair,
    *,
    reconcile: bool,
    allow_clear: bool,
    max_pins: int,
    thorough: bool,
    dry_run: bool,
    logger: logging.Logger,
) -> PairSummary:
    label = f"{pair.donor_id}→{pair.recipient_id}"
    summary = PairSummary(pair.donor_id, pair.recipient_id)

    rows = await db.get_messages_for_channel_pair(pair.donor_id, pair.recipient_id)
    pin_map, dupes = build_pin_map(rows)
    summary.dupes = dupes
    if dupes:
        logger.warning(f"[{label}] дубли binding_id для original_id: {dupes}")
    if not pin_map:
        logger.warning(
            f"[{label}] нет связок в binding_id — прогоните past_mode.py, пропуск пары"
        )
        return summary

    managed_ids = {r.mirror_id for r in rows}

    donor_pins = await fetch_pinned(
        client, pair.donor_id, pair.from_topics or None, max_pins, thorough, logger
    )
    desired, skipped = resolve_desired_pins(donor_pins, pin_map, logger, label)
    summary.desired = len(desired)
    summary.skipped_no_binding = skipped

    current_pins = await fetch_pinned(
        client, pair.recipient_id, pair.to_topics or None, max_pins, thorough, logger
    )
    current_ids = {m.id for m in current_pins}
    summary.already_pinned = len(set(desired) & current_ids)

    plan = plan_pin_actions(
        desired, current_ids, managed_ids, reconcile=reconcile, allow_clear=allow_clear
    )

    if not dry_run:
        # Закрепляем по возрастанию mirror_id (старые → новые). На чистом первом
        # прогоне это ставит новейший закреп донора сверху; при повторном прогоне
        # с уже существующими закрепами порядок точно не воспроизводится.
        for mid in plan.to_pin:
            await safe_call(
                client,
                lambda m=mid: client(
                    UpdatePinnedMessageRequest(
                        peer=pair.recipient_id, id=m, silent=True
                    )
                ),
                skip_errors=(errors.MessageIdInvalidError,),
            )
        for mid in plan.to_unpin:
            await safe_call(
                client,
                lambda m=mid: client(
                    UpdatePinnedMessageRequest(
                        peer=pair.recipient_id, id=m, unpin=True, silent=True
                    )
                ),
                skip_errors=(errors.MessageIdInvalidError,),
            )

    summary.pinned = len(plan.to_pin)
    summary.unpinned = len(plan.to_unpin)
    suffix = " (dry-run)" if dry_run else ""
    logger.info(
        f"[{label}] desired={summary.desired} already={summary.already_pinned} "
        f"pinned=+{summary.pinned} unpinned=-{summary.unpinned} "
        f"no-binding={summary.skipped_no_binding}{suffix}"
    )
    return summary


async def _run(logger: logging.Logger, args: argparse.Namespace) -> None:
    logger.warning(
        "sync_pins.py использует тот же SESSION_STRING, что и main.py. "
        "Убедитесь, что main.py НЕ запущен."
    )

    if USE_MEMORY_DB:
        logger.error(
            "USE_MEMORY_DB=true — связок нет. Сначала настройте Postgres и "
            "прогоните past_mode.py."
        )
        return

    pairs = iter_sync_directions(CHAT_MAPPING, BROADCAST_CHANNEL, args.include_broadcast)
    if args.only:
        wanted = set(args.only)
        pairs = [p for p in pairs if p.donor_id in wanted]
    if not pairs:
        logger.warning("Нет пар для синхронизации.")
        return

    logger.info(f"Пар для синхронизации: {len(pairs)}")

    db = await PostgresDatabase(connection_string=DB_URL)
    try:
        async with open_client(
            logger, warn_main_running=False, flood_sleep_threshold=60
        ) as (client, _me):
            # raw SearchRequest требует резолва peer из сессии — прогреваем кэш.
            peer_ids = {p.donor_id for p in pairs} | {p.recipient_id for p in pairs}
            for cid in peer_ids:
                await safe_call(
                    client, lambda c=cid: client.get_entity(c), skip_errors=(ValueError,)
                )

            totals = PairSummary(0, 0)
            for pair in pairs:
                try:
                    s = await sync_pair(
                        client,
                        db,
                        pair,
                        reconcile=not args.additive,
                        allow_clear=args.allow_clear,
                        max_pins=args.max_pins,
                        thorough=args.thorough,
                        dry_run=args.dry_run,
                        logger=logger,
                    )
                except Exception as e:
                    logger.error(
                        f"[{pair.donor_id}→{pair.recipient_id}] ошибка: "
                        f"{type(e).__name__}: {e}"
                    )
                    continue
                totals.desired += s.desired
                totals.pinned += s.pinned
                totals.unpinned += s.unpinned
                totals.skipped_no_binding += s.skipped_no_binding

            suffix = " (dry-run)" if args.dry_run else ""
            logger.info(
                f"Итого: desired={totals.desired} pinned=+{totals.pinned} "
                f"unpinned=-{totals.unpinned} no-binding={totals.skipped_no_binding}{suffix}"
            )
    finally:
        await db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Синхронизация закреплённых сообщений донор → получатель"
    )
    parser.add_argument("--dry-run", action="store_true", help="Только показать план")
    parser.add_argument(
        "--additive",
        action="store_true",
        help="Только закреплять недостающее, никогда не откреплять",
    )
    parser.add_argument(
        "--allow-clear",
        action="store_true",
        help="Разрешить откреп всех managed-закрепов, когда у донора не осталось ни одного",
    )
    parser.add_argument(
        "--include-broadcast",
        action="store_true",
        help="Также синхронизировать закрепы broadcast-канала",
    )
    parser.add_argument(
        "--thorough",
        action="store_true",
        help="Дополнительно опрашивать закрепы точечно по каждому топику форума",
    )
    parser.add_argument("--max-pins", type=int, default=100)
    parser.add_argument(
        "--only",
        type=int,
        action="append",
        metavar="DONOR_ID",
        help="Ограничить указанными донорами (можно повторять)",
    )
    args = parser.parse_args()

    logger = setup_stdout_logger("sync_pins", LOG_LEVEL)
    try:
        asyncio.run(_run(logger, args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
