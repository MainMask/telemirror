"""🛠 Обслуживание: skylon_set/restrict_saving.py and sync_pins.py, run as
``telemirror-task@<module>.service`` (Conflicts= with the live mirror)."""

import logging
import time
from typing import Optional

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.callback_answer import CallbackAnswer

from telemirror.panel import keyboards, settings, status, texts
from telemirror.panel.callbacks import Act, Nav
from telemirror.panel.runtime import Launch, Runtime
from telemirror.panel.systemd import Systemd, SystemdError, UnitState
from telemirror.panel.ui import Panel, Screen, show

logger = logging.getLogger(__name__)
router = Router(name="maintenance")


def build_task_args(key: str, dry: bool, flags: frozenset[str] = frozenset()) -> list[str]:
    """argv tail for the task unit — only whitelisted flags ever get in."""
    if key == "rs":
        if flags:
            raise ValueError("restrict_saving takes no flags")
        # --yes: no input() prompt (there's no terminal under systemd)
        return ["--dry-run"] if dry else ["--yes"]
    if key == "sp":
        unknown = flags - set(settings.SYNC_PINS_FLAGS)
        if unknown:
            raise ValueError(f"sync_pins: flags not allowed from the panel: {sorted(unknown)}")
        args = [f for f in settings.SYNC_PINS_FLAGS if f in flags]
        return args + ["--dry-run"] if dry else args
    raise ValueError(f"unknown task {key!r}")


def env_file_text(args: list[str]) -> str:
    return "TASK_ARGS=" + " ".join(args) + "\n"


def _flags(key: str, runtime: Runtime) -> frozenset[str]:
    return frozenset(runtime.sp_flags) if key == "sp" else frozenset()


def can_run_real(key: str, runtime: Runtime, st: Optional[UnitState]) -> bool:
    """A real run is offered only right after a successful dry-run with the
    same flags (that finished after it was launched)."""
    last = runtime.last_launch(key)
    if last is None or not last.dry or st is None or st.running:
        return False
    if last.args != tuple(build_task_args(key, True, _flags(key, runtime))):
        return False
    return st.result == "success" and st.since is not None and st.since >= int(last.at)


def _last_text(runtime: Runtime, key: str, st: Optional[UnitState]) -> str:
    last = runtime.last_launch(key)
    if last is None:
        return texts.LAST_NEVER
    if st is not None and st.running:
        result = texts.RESULT_RUNNING
    elif st is not None and st.result == "success":
        result = texts.RESULT_OK
    else:
        result = texts.RESULT_FAIL.format(result=texts.esc(st.result if st else texts.NO_DATA))
    return texts.LAST_RUN.format(
        kind=texts.KIND_DRY if last.dry else texts.KIND_REAL, state=result, when=texts.fmt_ts(int(last.at))
    )


async def task_screen(sysd: Systemd, runtime: Runtime, key: str) -> Screen:
    st = await status.unit_state(sysd, key)
    template = texts.RS_TITLE if key == "rs" else texts.SP_TITLE
    text = template.format(last=_last_text(runtime, key, st))
    if not sysd.available:
        text += "\n\n" + texts.SYSTEMD_UNAVAILABLE
    flags = set(runtime.sp_flags) if key == "sp" else None
    return text, keyboards.task_screen(key, can_run_real(key, runtime, st), flags)


@router.callback_query(Nav.filter(F.s == "mnt"))
async def on_maintenance(callback: CallbackQuery, bot: Bot, panel: Panel) -> None:
    await show(callback, bot, panel, (texts.MAINTENANCE_TITLE, keyboards.maintenance()))


@router.callback_query(Nav.filter(F.s.in_(settings.TASK_MODULES)))
async def on_task(
    callback: CallbackQuery, callback_data: Nav, bot: Bot, panel: Panel, sysd: Systemd, runtime: Runtime
) -> None:
    await show(callback, bot, panel, await task_screen(sysd, runtime, callback_data.s))


@router.callback_query(Act.filter(F.a == "spf"), Act.filter(F.p == "sp"))
async def on_flag(
    callback: CallbackQuery, callback_data: Act, bot: Bot, panel: Panel, sysd: Systemd, runtime: Runtime
) -> None:
    if 0 <= callback_data.i < len(settings.SYNC_PINS_FLAGS):
        flag = settings.SYNC_PINS_FLAGS[callback_data.i]
        runtime.sp_flags ^= {flag}
    await show(callback, bot, panel, await task_screen(sysd, runtime, "sp"))


@router.callback_query(Act.filter(F.a == "run"), Act.filter(F.p.in_(settings.TASK_MODULES)))
async def on_run(
    callback: CallbackQuery, callback_data: Act, callback_answer: CallbackAnswer,
    bot: Bot, panel: Panel, sysd: Systemd, runtime: Runtime,
) -> None:
    key, dry = callback_data.p, callback_data.i == 0
    title = texts.UNIT_TITLES[key]
    if not sysd.available:
        callback_answer.text = texts.SYSTEMD_UNAVAILABLE
        callback_answer.show_alert = True
        return
    running = await status.running_exclusive(sysd)
    if running:
        callback_answer.text = texts.TASK_BUSY.format(title=texts.UNIT_TITLES[running[0]])
        callback_answer.show_alert = True
        return
    if not dry and not can_run_real(key, runtime, await status.unit_state(sysd, key)):
        callback_answer.text = texts.RUN_NEEDS_DRY
        callback_answer.show_alert = True
        return
    if not callback_data.ok:
        text = texts.CONFIRM_RUN.format(
            title=title,
            kind=texts.KIND_DRY if dry else texts.KIND_REAL,
            what=texts.WHAT_DRY if dry else texts.WHAT_REAL,
        )
        yes = Act(a="run", p=key, i=callback_data.i, ok=True)
        await show(callback, bot, panel, (text, keyboards.confirm(yes, Nav(s=key))))
        return
    left = runtime.cooldown_left(key)
    if left:
        callback_answer.text = texts.COOLDOWN.format(sec=left)
        callback_answer.show_alert = True
        return
    args = build_task_args(key, dry, _flags(key, runtime))
    module = settings.TASK_MODULES[key]
    try:
        settings.TASK_ENV_DIR.mkdir(parents=True, exist_ok=True)
        (settings.TASK_ENV_DIR / f"{module}.env").write_text(env_file_text(args), encoding="utf-8")
        await sysd.start(settings.UNITS[key])
    except (OSError, SystemdError) as e:
        logger.error("panel: launching %s failed: %s", settings.UNITS[key], e)
        callback_answer.text = texts.SYSTEMD_ERROR.format(detail=str(e)[:150])
        callback_answer.show_alert = True
        return
    runtime.launches[key] = Launch(tuple(args), dry, time.time())
    runtime.mark_started(key)
    logger.info("panel: started %s %s by admin %s", settings.UNITS[key], args, callback.from_user.id)
    callback_answer.text = texts.TASK_STARTED
    await show(callback, bot, panel, await task_screen(sysd, runtime, key))
