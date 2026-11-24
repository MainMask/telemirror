"""🛠 Инструменты: the ``telemirror.tasks`` scripts check_access,
restrict_saving, sync_pins, anonymize_groups and clear_channels for a project,
run as ``telemirror-task@<key>.service`` on its session (its mirror is paused
meanwhile). A real run only after a successful check (dry-run)."""

import json
import logging
import re
import time
from typing import Optional

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import configedit, configparse, configstore, filtercatalog, registry, settings, status, texts
from bot.callbacks import ActCB, NavCB
from bot.configparse import ConfigError
from bot.keyboards.common import pick_kb
from bot.registry import CHECK, CHECKED, RUN, SCREENS, TITLES, UNCHECKED, YES, YES_DELETE, title
from bot.routers import _units
from bot.routers._common import (
    confirmed,
    input_kind,
    message_of,
    on_action,
    stale_tap,
    start_form,
)
from bot.runtime import Launch, Runtime
from bot.screens import show, view
from bot.states import Input, leave_form
from bot.systemd import Systemd, UnitState
from bot.texts import esc, head
from telemirror.projects import Project, access_report_path

logger = logging.getLogger(__name__)
router = Router(name="maintenance")

TASKS = ("ca", "rs", "sp", "ag", "cc")  # screen id = task id (settings.TASK_MODULES)

ABOUT = {
    "ca": "Проверяет каждый канал проекта: источники и канал рассылки аккаунт должен видеть, а в ваших "
          "каналах — иметь право публиковать. Ничего не меняет. Заодно запоминает "
          "названия каналов для этого меню.",
    "rs": "Включает в ваших каналах запрет сохранять и пересылать посты. Где он уже включён — пропускает.",
    "sp": "Закрепляет в ваших каналах копии постов, закреплённых в источниках (работает, только если у "
          "зеркала есть база данных). По умолчанию открепляет то, что открепили в источнике, — только "
          "среди постов, которые скопировало зеркало. Настройки запуска действуют и на проверку, и на "
          "выполнение.",
    "ag": "Во всех группах, где аккаунт проекта — администратор (не только в ваших каналах): скрывает, "
          "кто из админов пишет, затем скрывает список участников (Telegram позволяет это только "
          "достаточно большим группам). Где уже включено — пропускает.",
    "cc": "Удаляет все посты в ваших каналах проекта (в темах групп — только в темах из настроек) и "
          f"забывает, что уже было скопировано, — после этого {registry.REPLAY} скопирует всё заново.",
}
# what must be seen before a run, not folded under the screen
WARNING = {"cc": "⚠️ Удаляет <b>все</b> посты в ваших каналах. Вернуть нельзя."}

def build_task_args(task: str, dry: bool, flags: frozenset = frozenset(), opts: Optional[dict] = None) -> list:
    """argv tail for the task unit — only whitelisted flags and integer options
    ever get in."""
    opts = opts or {}
    if opts and task != "sp":
        raise ValueError(f"{task}: takes no options")
    if task == "ca":  # read-only: nothing to check first, no flags
        if flags:
            raise ValueError("check_access takes no flags")
        return []
    if task in ("rs", "ag", "cc"):
        if flags:
            raise ValueError(f"{settings.TASK_MODULES[task]} takes no flags")
        # --yes: no input() prompt (there's no terminal under systemd)
        return ["--dry-run"] if dry else ["--yes"]
    if task == "sp":
        unknown = flags - set(settings.SYNC_PINS_FLAGS)
        if unknown:
            raise ValueError(f"sync_pins: flags not allowed from the panel: {sorted(unknown)}")
        args = [f for f in settings.SYNC_PINS_FLAGS if f in flags]
        if (max_pins := opts.get("max_pins")) is not None:
            low, high = settings.SYNC_PINS_MAX_PINS
            if type(max_pins) is not int or not low <= max_pins <= high:
                raise ValueError(f"sync_pins: bad --max-pins {max_pins!r}")
            args += ["--max-pins", str(max_pins)]
        for donor in opts.get("only", ()):
            if type(donor) is not int or not re.fullmatch(r"-100\d{5,}", str(donor)):
                raise ValueError(f"sync_pins: bad --only {donor!r}")
            args += ["--only", str(donor)]
        return args + ["--dry-run"] if dry else args
    raise ValueError(f"unknown task {task!r}")


def env_file_text(task: str, args: list) -> str:
    return f"TASK_MODULE={settings.TASK_MODULES[task]}\nTASK_ARGS=" + " ".join(args) + "\n"


def _args(task: str, dry: bool, project: Project, runtime: Runtime) -> list:
    if task != "sp":
        return build_task_args(task, dry)
    return build_task_args(task, dry, frozenset(runtime.flags(project.key)), runtime.opts(project.key))


def config_sha(project: Project) -> str:
    try:
        return configstore.sha(project.config_path.read_text(encoding="utf-8"))
    except OSError:
        return ""


def can_run_real(task: str, project: Project, runtime: Runtime, st: Optional[UnitState]) -> bool:
    """A real run is offered only right after a successful dry-run with the
    same flags, options and config (that finished after it was launched, by
    itself — not stopped halfway) — a channel added since was never in the
    plan the check showed. The task
    unit is shared by all the project's tasks: that check must also be its
    last run — not another task's success after it."""
    last = runtime.last_launch(project.key, task)
    if last is None or not last.dry or st is None or st.running:
        return False
    if any(launch.at > last.at for (key, _), launch in runtime.launches.items() if key == project.key):
        return False
    if last.args != tuple(_args(task, True, project, runtime)) or last.config != config_sha(project):
        return False
    return (st.result == "success" and st.completed
            and st.since is not None and st.since >= int(last.at))


def _last_text(runtime: Runtime, project: Project, task: str, st: Optional[UnitState]) -> str:
    last = runtime.last_launch(project.key, task)
    if last is None:
        return "ещё не запускался (с последнего перезапуска панели)"
    if st is not None and st.running:
        result = "выполняется"
    elif st is not None and st.result == "success":
        result = "успешно" if st.completed else texts.result_text("signal")  # stopped from outside
    else:
        result = texts.result_text(st.result) if st else texts.NO_DATA
    return f"{'проверка' if last.dry else 'выполнение'} — {result}, {texts.fmt_ts(last.at)}"


ROLES = {"source": "источник", "target": "ваш канал", "broadcast": "рассылка"}
REASONS = {"not_member": "аккаунт не состоит в этом канале (или ID неверный)",
           "cannot_post": "у аккаунта нет права публиковать"}


def access_text(project: Project) -> str:
    """The last 🛂 Проверка доступа report (problems first) — written by the task itself."""
    try:
        report = json.loads(access_report_path(project.key).read_text(encoding="utf-8"))
        rows, at = list(report["chats"]), float(report["at"])
    except (OSError, ValueError, KeyError, TypeError):
        return f"<i>Отчёта ещё нет — нажмите {title('ca_dry')}.</i>"
    bad = [r for r in rows if not r.get("ok")]
    notes = [r for r in rows if r.get("ok") and r.get("note") == "noforwards"]
    lines = [f"<b>Отчёт от {texts.fmt_ts(at)}:</b> ✅ {len(rows) - len(bad)} · ❌ {len(bad)}"]

    def name(r: dict) -> str:
        roles = ", ".join(ROLES.get(x, x) for x in r.get("roles", []))
        title_ = r.get("title")
        return (f"<b>{esc(title_)}</b>" if title_ else f"<code>{esc(r.get('id'))}</code>") + f" ({roles})"

    lines += [f"❌ {name(r)} — {REASONS.get(r.get('reason'), esc(r.get('reason')))}" for r in bad[:settings.ACCESS_REPORT_ROWS]]
    if len(bad) > settings.ACCESS_REPORT_ROWS:
        lines.append(f"… и ещё {len(bad) - settings.ACCESS_REPORT_ROWS} — в {title('ca_log')}")
    lines += [f"ℹ️ {name(r)} — в источнике запрещено сохранение: фото и видео скопируются только с фильтром "
              f"«{filtercatalog.display_name('RestrictSavingContentBypassFilter')}»"
              for r in notes[:settings.ACCESS_REPORT_ROWS]]
    return "\n".join(lines)


# sync_pins flags: registry button → flag (settings.SYNC_PINS_FLAGS, the same order)
SP_FLAG_OF = dict(zip(("sp_additive", "sp_allow_clear", "sp_broadcast", "sp_thorough"), settings.SYNC_PINS_FLAGS, strict=True))


def _screen(project: Project, task: str) -> NavCB:
    return NavCB(s=task, p=project.key)


@view("ca")
@view("rs")
@view("sp")
@view("ag")
@view("cc")
async def task_view(message: Message, edit: bool, nav: NavCB, *, project: Project, sysd: Systemd,
                    runtime: Runtime, note: str = "", journal: bool = False, **_) -> None:
    """``journal``: 📄 Журнал — the task unit's last run under the screen's text."""
    task = nav.s
    st = await status.unit_state(sysd, project.task_unit)
    body = "\n\n".join(filter(None, [WARNING.get(task, ""),
                                      f"Последний запуск: {_last_text(runtime, project, task, st)}"]))
    if task == "ca":
        body += "\n\n" + access_text(project)
    if not sysd.available:
        body += "\n\n" + texts.SYSTEMD_UNAVAILABLE
    titles = {}
    if task == "sp":
        flags, opts = runtime.flags(project.key), runtime.opts(project.key)
        for action, flag in SP_FLAG_OF.items():
            titles[action] = (CHECKED if flag in flags else UNCHECKED) + title(action).removeprefix(CHECKED)
        only = opts.get("only", ())
        titles["sp_max"] = f"{title('sp_max')}: {opts.get('max_pins', settings.SYNC_PINS_DEFAULT_MAX_PINS)}"
        titles["sp_only"] = f"{title('sp_only')}: {len(only) if only else 'все'}"
        if only:
            names = status.project_info(project).names
            body += "\n\nВыбранные источники: " + texts.refs(only, names)
            if texts.any_unnamed(only, names):
                body += "\n" + texts.NAMES_LATER
    if journal:
        body += "\n\n" + (await _units.journal_text(sysd, project.task_unit, st) or "<i>Журнал пуст.</i>")
    hidden: tuple = () if can_run_real(task, project, runtime, st) else (f"{task}_run",)
    if hidden and task != "ca":  # ca only checks
        body += f"\n\n<i>«{RUN}» появится здесь после успешной проверки — «{CHECK}» с этими же настройками.</i>"
    if not (sysd.available and st is not None and st.running):
        hidden += (f"{task}_stop",)
    await show(message, edit, task, project, body=body, more=ABOUT[task], note=note, titles=titles, hidden=hidden,
               pg=nav.pg)


async def _reopen(message: Message, project: Project, task: str, deps: dict, note: str = "") -> None:
    await task_view(message, True, _screen(project, task), project=project, note=note, **deps)


@on_action(router, *SP_FLAG_OF)
async def on_flag(callback: CallbackQuery, callback_data: ActCB, project: Project, runtime: Runtime,
                  deps: dict) -> None:
    runtime.flags(project.key).symmetric_difference_update({SP_FLAG_OF[callback_data.a]})
    await callback.answer()
    await _reopen(message_of(callback), project, "sp", deps)


SP_ASKS = {
    "sp_max": "Сколько закрепов просматривать в каждом чате или теме группы.\n\n"
              "Пришлите число от {low} до {high}, например "
              f"<code>{settings.SYNC_PINS_DEFAULT_MAX_PINS}</code>.\n\n"
              f"<code>-</code> — вернуть значение по умолчанию ({settings.SYNC_PINS_DEFAULT_MAX_PINS}).",
    "sp_only": "У каких источников переносить закрепы?\n\n"
               f"Нажмите {head(TITLES['pick'])}, перешлите пост из источника или пришлите ID источников через "
               "запятую — закрепы перенесутся только у них.\n\n"
               "<code>-</code> — снова у всех источников.",
}


def donors_of(project: Project) -> set:
    """The project's sources (and its broadcast channel) — what --only may name."""
    data = status.project_info(project).data
    ids = {configparse.chat_of(configparse.ref_str(r)) for d in configedit.directions(data) for r in d.get("from") or []}
    if isinstance(data.get("broadcast_channel"), int):
        ids.add(data["broadcast_channel"])
    return ids


@on_action(router, "sp_max", "sp_only")
async def on_option(callback: CallbackQuery, callback_data: ActCB, project: Project, state: FSMContext,
                    runtime: Runtime) -> None:
    opts = runtime.opts(project.key)
    if callback_data.a == "sp_max":
        current = str(opts.get("max_pins", settings.SYNC_PINS_DEFAULT_MAX_PINS))
    else:
        current = texts.refs(opts["only"], status.project_info(project).names) if opts.get("only") else "все"
    low, high = settings.SYNC_PINS_MAX_PINS
    await start_form(
        callback, state, Input.value,
        f"{head(title(callback_data.a))} — сейчас: {current}.\n\n{SP_ASKS[callback_data.a].format(low=low, high=high)}",
        _screen(project, "sp"), markup=pick_kb() if callback_data.a == "sp_only" else None,
        data={"kind": callback_data.a, "p": project.key},
    )


@input_kind("sp_max")
@input_kind("sp_only")
async def set_option(message: Message, state: FSMContext, raw: str, data: dict, project: Project,
                     runtime: Runtime, deps: dict, **_) -> None:
    opts = runtime.opts(project.key)
    if raw == configparse.CLEAR:
        opts.pop("max_pins" if data["kind"] == "sp_max" else "only", None)
    elif data["kind"] == "sp_max":
        low, high = settings.SYNC_PINS_MAX_PINS
        if not raw.isdigit() or not low <= int(raw) <= high:
            raise ConfigError("bad_max_pins", raw)
        opts["max_pins"] = int(raw)
    else:
        donors = [configparse.chat_of(r) for r in configparse.parse_chat_refs(raw)]
        if unknown := [d for d in donors if d not in donors_of(project)]:
            names = status.project_info(project).names
            await message.answer(f"⚠️ Это не источники проекта: {texts.refs(unknown, names)}\n{texts.SEND_AGAIN}")
            return
        opts["only"] = tuple(dict.fromkeys(donors))
    await leave_form(message.chat.id, state)
    await task_view(message, False, _screen(project, "sp"), project=project,
                    note=f"✅ Запомнено. Перед «{RUN}» нужна новая проверка с этими настройками.", **deps)


RUNNING = "⛔ Инструмент этого проекта уже работает — дождитесь, пока закончит."
NEED_CHECK = "⛔ Сначала нажмите «🔍 Проверить» и дождитесь, пока проверка успешно закончится (с теми же настройками)."


async def _runnable(callback: CallbackQuery, project: Project, task: str, dry: bool, sysd: Systemd,
                    runtime: Runtime) -> bool:
    """False after saying why it can't run now (asked again at «Да»: the unit
    may have started, or the flags changed, since the question)."""
    if not await _units.can_start(callback, sysd, runtime, project, project.task_unit):
        return False
    st = await status.unit_state(sysd, project.task_unit)
    if st is not None and st.running:
        await stale_tap(callback, RUNNING)
        return False
    if not dry and not can_run_real(task, project, runtime, st):
        await stale_tap(callback, NEED_CHECK)
        return False
    return True


@on_action(router, *(f"{t}_{m}" for t in TASKS for m in ("dry", "run") if f"{t}_{m}" != "ca_run"))
async def on_run(callback: CallbackQuery, callback_data: ActCB, project: Project, state: FSMContext,
                 sysd: Systemd, runtime: Runtime, deps: dict) -> None:
    task, mode = callback_data.a.split("_")
    dry = mode == "dry"
    if not await _runnable(callback, project, task, dry, sysd, runtime):
        return
    if dry:
        what = "Проверка ничего не меняет — только показывает, что будет сделано."
    elif task == "cc":
        what = "⚠️ Все посты в ваших каналах проекта будут удалены. Вернуть нельзя."
    else:
        what = "⚠️ В каналах будут сделаны изменения, которые показала проверка."
    question = f"{head(SCREENS[task].title)}: {'проверка' if dry else 'выполнение'}?\n\n{what}"
    # a check only reads: asked only when it stops something; a real run always
    if await _units.ask_start(callback, state, sysd, project, project.task_unit, question, _screen(project, task),
                              always=not dry, kind="task", yes=YES_DELETE if task == "cc" and not dry else YES,
                              task=task, dry=dry):
        await _run(callback, project, task, dry, sysd, runtime, deps)


@confirmed("task")
async def do_run(callback: CallbackQuery, action: dict, project: Project, sysd: Systemd, runtime: Runtime,
                 deps: dict, **_) -> None:
    if await _runnable(callback, project, action["task"], action["dry"], sysd, runtime):
        await _run(callback, project, action["task"], action["dry"], sysd, runtime, deps)


async def _run(callback: CallbackQuery, project: Project, task: str, dry: bool, sysd: Systemd,
               runtime: Runtime, deps: dict) -> None:
    args = _args(task, dry, project, runtime)
    try:
        settings.TASK_ENV_DIR.mkdir(parents=True, exist_ok=True)
        (settings.TASK_ENV_DIR / f"{project.key}.env").write_text(env_file_text(task, args), encoding="utf-8")
    except OSError as e:
        logger.error("panel: writing the env of %s failed: %s", project.task_unit, e)
        await stale_tap(callback, texts.SYSTEMD_ERROR.format(detail=str(e)[:150]))
        return
    if not await _units.launch(callback, sysd, runtime, project, project.task_unit):
        return
    runtime.launches[(project.key, task)] = Launch(tuple(args), dry, time.time(), config_sha(project))
    logger.info("panel: started %s %s %s", project.task_unit, task, args)
    await _reopen(message_of(callback), project, task, deps,
                  f"▶️ {'Проверка запущена' if dry else 'Выполнение запущено'}. Что происходит — {title(task + '_log')}.")


@on_action(router, *(f"{t}_stop" for t in TASKS))
async def on_stop(callback: CallbackQuery, callback_data: ActCB, project: Project, state: FSMContext,
                  sysd: Systemd) -> None:
    task = callback_data.a.removesuffix("_stop")
    await _units.ask_stop(callback, state, sysd, project, project.task_unit, False, _screen(project, task))


@on_action(router, *(f"{t}_log" for t in TASKS))
async def on_log(callback: CallbackQuery, callback_data: ActCB, project: Project, deps: dict) -> None:
    await callback.answer()
    task = callback_data.a.removesuffix("_log")
    await task_view(message_of(callback), True, _screen(project, task), project=project, journal=True, **deps)
