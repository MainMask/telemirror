"""
Включает «Restrict Saving Content» (флаг ``noforwards`` — запрет копирования и
пересылки контента подписчиками) во всех каналах и супергруппах-получателях:
живых (CHAT_MAPPING из mirror.config.yml) и курсовых
(citadel_courses.config.yml, который config.py сам не читает).

Использование:
    python -m skylon_set.restrict_saving            # с подтверждением
    python -m skylon_set.restrict_saving --dry-run  # только показывает план

Предупреждение: использует тот же SESSION_STRING, что и основной сервис.
Не запускайте одновременно с main.py.
"""

import argparse
import asyncio
import functools
import logging
import sys
from pathlib import Path
from typing import Set

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from config import CHAT_MAPPING, LOG_LEVEL
except Exception:
    print("Failed reading .env")
    raise

import yaml
from telethon.errors import ChatAdminRequiredError, RightForbiddenError
from telethon.tl.functions.messages import ToggleNoForwardsRequest

from telemirror.misc.log_setup import setup_stdout_logger
from skylon_set._common import open_client
from skylon_set._common import safe_call as _safe_call

# Курсовой конфиг config.py не грузит (его читает только past_mode.py), но
# Restrict Saving нужен и на курсовых получателях — берём id прямо из файла,
# как это делает setup_mirrors.step_final_verify.
COURSES_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / ".configs" / "citadel_courses.config.yml"
)

# ToggleNoForwards fails with these when the account isn't admin of a recipient —
# treat as "skip", like a private channel (same handling as anonymize_groups.py).
safe_call = functools.partial(
    _safe_call, skip_errors=(ChatAdminRequiredError, RightForbiddenError)
)


def collect_recipient_ids(chat_mapping) -> Set[int]:
    """Собирает множество id каналов-получателей из CHAT_MAPPING.

    Топики не важны — ``noforwards`` выставляется на уровне чата.
    """
    return {tgt_id for tgt_map in chat_mapping.values() for tgt_id in tgt_map}


def course_recipient_ids(path: Path = COURSES_CONFIG_PATH) -> Set[int]:
    """id получателей из citadel_courses.config.yml (пусто, если файла нет)."""
    if not path.exists():
        return set()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        int(str(target).split("#")[0])
        for direction in data.get("directions", [])
        for target in direction.get("to", [])
    }


async def _run(logger: logging.Logger, dry_run: bool) -> None:
    recipient_ids = collect_recipient_ids(CHAT_MAPPING) | course_recipient_ids()
    if not recipient_ids:
        logger.warning("CHAT_MAPPING пуст — нечего настраивать.")
        return

    async with open_client(logger) as (client, _me):
        already, targets, unavailable = [], [], []
        for chat_id in sorted(recipient_ids):
            try:
                entity = await safe_call(
                    client, lambda i=chat_id: client.get_entity(i)
                )
            except Exception as e:
                logger.error(f"[{chat_id}] не удалось получить сущность: {e}")
                entity = None
            if entity is None:
                unavailable.append(chat_id)
            elif getattr(entity, "noforwards", False):
                already.append(entity)
            else:
                targets.append(entity)

        def titles(lst):
            return ", ".join(getattr(e, "title", str(e)) for e in lst) if lst else "—"

        logger.info(f"Уже включено ({len(already)}):     {titles(already)}")
        logger.info(f"Требуют включения ({len(targets)}): {titles(targets)}")
        logger.info(f"Недоступны ({len(unavailable)}):      {unavailable or '—'}")

        if not targets:
            logger.info("Restrict Saving Content уже включён у всех получателей.")
            return

        if dry_run:
            logger.info(
                f"(dry-run) Было бы включено в {len(targets)} чатах."
            )
            return

        answer = input(
            f"\nВключить Restrict Saving Content в {len(targets)} чатах? [y/N] "
        ).strip().lower()
        if answer != "y":
            logger.info("Отменено.")
            return

        for entity in targets:
            result = await safe_call(
                client,
                lambda e=entity: client(
                    ToggleNoForwardsRequest(peer=e, enabled=True)
                ),
            )
            logger.info(
                f"  {getattr(entity, 'title', str(entity))}: "
                + ("OK" if result is not None else "ОШИБКА")
            )

        errors = []
        for entity in targets:
            fresh = await safe_call(
                client, lambda e=entity: client.get_entity(e)
            )
            if not (fresh and getattr(fresh, "noforwards", False)):
                errors.append(getattr(entity, "title", str(entity)))

        if errors:
            logger.error(
                f"Не удалось включить в {len(errors)} чатах: {', '.join(errors)}"
            )
        else:
            logger.info("Всё OK — Restrict Saving Content включён у всех получателей.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Включить Restrict Saving Content у получателей telemirror"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Только показать план, без реальных изменений",
    )
    args = parser.parse_args()

    logger = setup_stdout_logger("restrict_saving", LOG_LEVEL)
    try:
        asyncio.run(_run(logger, args.dry_run))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
