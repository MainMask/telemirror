"""The one way a screen saves a config change: ⏳ "validating…" → the store
operation → the screen reopened with the outcome on top, or the refusal with
⬅️ back."""

import logging
from typing import Any, Awaitable, Callable, Optional, Union

from aiogram.types import Message

from bot import status, texts
from bot.callbacks import NavCB
from bot.configparse import ConfigError
from bot.keyboards.common import back_kb
from bot.screens import open_screen, send
from telemirror.projects import Project

logger = logging.getLogger(__name__)

Reopen = Callable[[Message, str], Awaitable[Any]]  # (the ⏳ message, the note) → shows the screen


async def saved_note(project: Project, deps: dict) -> str:
    """✅ Сохранено — and whether a restart is needed for it to apply."""
    live = await status.unit_state(deps["sysd"], project.live_unit)
    return texts.SAVED if live is not None and live.running else texts.SAVED_STOPPED


async def save(
    message: Message,
    edit: bool,
    project: Project,
    op: Callable[[Project], Awaitable[Any]],
    reopen: Union[NavCB, Reopen],
    deps: dict,
    *,
    back: Optional[NavCB] = None,
    outcome: Callable[[str], str] = lambda done: done,
) -> bool:
    """Run ``op`` (a ConfigStore call); ⏳ in the message's place (``edit``) or as
    a new one, then ``reopen`` (a screen, or what shows one not opened by
    NavCB) in the ⏳ message's place, ``outcome`` of the saved note on top.
    A refusal comes with ⬅️ to ``back`` (default: ``reopen``)."""
    back = back or (reopen if isinstance(reopen, NavCB) else None)
    kb = back_kb(back) if back else None
    if not project.session_path.exists():
        # the validator loads telemirror.config as the project's service would — its session included
        await send(message, edit)(texts.SESSION_MISSING, reply_markup=kb)
        return False
    # Validation imports telemirror.config in a subprocess — seconds; say so first.
    wait = await send(message, edit)(texts.VALIDATING)
    target = wait if isinstance(wait, Message) else message
    try:
        await op(project)
    except ConfigError as e:
        logger.warning("panel: config write to %s refused: %s", project.config, e)
        await target.edit_text(texts.config_error(e.code, e.detail), reply_markup=kb)
        return False
    logger.info("panel: %s updated", project.config)
    done = outcome(await saved_note(project, deps))
    if isinstance(reopen, NavCB):
        await open_screen(reopen, target, True, deps, note=done)
    else:
        await reopen(target, done)
    return True
