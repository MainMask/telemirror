"""The one way a screen saves a config change: ⏳ "validating…" → the store
operation → the resulting screen with the outcome on top, or the refusal with
⬅️ back."""

import logging
from typing import Any, Awaitable, Callable, Optional

from aiogram.types import Message

from telemirror.panel import status, texts
from telemirror.panel.callbacks import NavCB
from telemirror.panel.configstore import ConfigError
from telemirror.panel.keyboards.common import back_kb
from telemirror.panel.screens import send
from telemirror.panel.systemd import Systemd
from telemirror.projects import Project

logger = logging.getLogger(__name__)

After = Callable[[Message, str], Awaitable[Any]]  # (the ⏳ message, the note) → shows the screen


async def save(
    message: Message,
    edit: bool,
    project: Project,
    op: Callable[[Project], Awaitable[Any]],
    after: After,
    back: NavCB,
    sysd: Systemd,
    *,
    done: Optional[str] = None,
) -> bool:
    """Run ``op`` (a ConfigStore call); ⏳ in the message's place (``edit``) or as
    a new one, then ``after`` shows the result in the ⏳ message's place."""
    if not project.session_path.exists():
        # the validator loads config.py as the project's service would — its session included
        await send(message, edit)(texts.SESSION_MISSING, reply_markup=back_kb(back))
        return False
    # Validation imports config.py in a subprocess — seconds; say so first.
    wait = await send(message, edit)(texts.VALIDATING)
    target = wait if isinstance(wait, Message) else message
    try:
        await op(project)
    except ConfigError as e:
        logger.warning("panel: config write to %s refused: %s", project.config, e)
        await target.edit_text(texts.config_error(e.code, e.detail), reply_markup=back_kb(back))
        return False
    logger.info("panel: %s updated", project.config)
    if done is None:
        live = await status.unit_state(sysd, project.live_unit)
        done = texts.SAVED if live is not None and live.running else texts.SAVED_STOPPED
    await after(target, done)
    return True
