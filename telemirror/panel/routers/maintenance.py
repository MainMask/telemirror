"""🛠 Обслуживание: skylon_set/check_access.py, restrict_saving.py, sync_pins.py,
anonymize_groups.py and clear_channels.py for a project, run as ``telemirror-task@<key>.service`` on its session (its mirror
is paused meanwhile). A real run only after a successful check (dry-run)."""

import json
import logging
import re
import time
from typing import Optional

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from telemirror.panel import configstore, settings, status, texts, turns
from telemirror.panel.callbacks import ActCB, NavCB
from telemirror.panel.configstore import ConfigError
from telemirror.panel.keyboards.common import button
from telemirror.panel.registry import SCREENS, YES, YES_DELETE, title
from telemirror.panel.routers._common import (
    ask_confirm,
    confirmed,
    input_kind,
    leave_form,
    message_of,
    on_action,
    project_of,
    session_ok,
    stale_tap,
    start_form,
)
from telemirror.panel.routers.projects import pause_text
from telemirror.panel.routers.tasks import show_unit
from telemirror.panel.runtime import Launch, Runtime
from telemirror.panel.screens import esc, head, show, view
from telemirror.panel.states import Input
from telemirror.panel.systemd import Systemd, SystemdError, UnitState
from telemirror.projects import Project, access_report_path

logger = logging.getLogger(__name__)
router = Router(name="maintenance")

ABOUT = {
    "ca": "Проверяет каждый канал из конфигурации проекта: источники и канал рассылки аккаунт "
          "должен видеть, в получателях и техканале — иметь право публиковать. Ничего не меняет. "
          "Темы (<code>#5</code>) не проверяются — только сами чаты.",
    "rs": "Включает «Запрет копирования» (noforwards) во всех каналах-получателях проекта. "
          "Где он уже включён — пропускается.",
    "sp": "Копирует закреплённые сообщения доноров на их зеркала (нужна БД Postgres: связи из "
          "таблицы binding_id). По умолчанию снимает закрепы, которые снял донор, — только у "
          "сообщений, созданных зеркалом.",
    "ag": "Во всех супергруппах, где аккаунт проекта — администратор (не только в получателях): "
          "включает «Анонимность» администратора, затем «Скрыть участников» (Telegram даёт это "
          "только достаточно большим группам). Где уже включено — пропускается.",
    "cc": "⚠️ Удаляет <b>все</b> сообщения в каналах-получателях проекта (в темах — только в "
          "темах из конфигурации) и сбрасывает в БД связи сообщений и прогресс догрузки по ним — "
          "после этого ⏪ Догрузка скопирует историю заново. Необратимо.",
}
SP_FLAGS = {
    "--additive": "Только добавлять (не снимать)",
    "--allow-clear": "Снимать все, если у донора закрепов нет",
    "--include-broadcast": "Включая канал рассылки",
    "--thorough": "Тщательно: опрашивать каждую тему",
}


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
    same flags, options and config (that finished after it was launched) — a
    channel added since was never in the plan the check showed. The task
    unit is shared by all the project's tasks: that check must also be its
    last run — not another task's success after it."""
    last = runtime.last_launch(project.key, task)
    if last is None or not last.dry or st is None or st.running:
        return False
    if any(launch.at > last.at for (key, _), launch in runtime.launches.items() if key == project.key):
        return False
    if last.args != tuple(_args(task, True, project, runtime)) or last.config != config_sha(project):
        return False
    return st.result == "success" and st.since is not None and st.since >= int(last.at)


def _last_text(runtime: Runtime, project: Project, task: str, st: Optional[UnitState]) -> str:
    last = runtime.last_launch(project.key, task)
    if last is None:
        return "в этой сессии панели не запускался"
    if st is not None and st.running:
        result = "выполняется"
    elif st is not None and st.result == "success":
        result = "успешно"
    else:
        result = f"ошибка ({esc(st.result if st else texts.NO_DATA)})"
    return f"{'проверка' if last.dry else 'выполнение'} — {result}, {texts.fmt_ts(last.at)}"


ROLES = {"source": "источник", "target": "получатель", "broadcast": "рассылка", "tech": "техканал"}
REASONS = {"not_member": "аккаунт не состоит в чате (или ID неверный)", "cannot_post": "нет права публиковать"}
REPORT_ROWS = 15  # problems listed on the screen (the journal has them all)


def access_text(project: Project) -> str:
    """The last 🛂 Доступ report (problems first) — written by the task itself."""
    try:
        report = json.loads(access_report_path(project.key).read_text(encoding="utf-8"))
        rows, at = list(report["chats"]), float(report["at"])
    except (OSError, ValueError, KeyError, TypeError):
        return "<i>Отчёта ещё нет — нажмите 🔍 Проверить.</i>"
    bad = [r for r in rows if not r.get("ok")]
    notes = [r for r in rows if r.get("ok") and r.get("note") == "noforwards"]
    lines = [f"<b>Отчёт от {texts.fmt_ts(at)}:</b> ✅ {len(rows) - len(bad)} · ❌ {len(bad)}"]

    def name(r: dict) -> str:
        roles = ", ".join(ROLES.get(x, x) for x in r.get("roles", []))
        return f"<code>{esc(r.get('id'))}</code> {esc(r.get('title') or '')} ({roles})"

    lines += [f"❌ {name(r)} — {REASONS.get(r.get('reason'), esc(r.get('reason')))}" for r in bad[:REPORT_ROWS]]
    if len(bad) > REPORT_ROWS:
        lines.append(f"… и ещё {len(bad) - REPORT_ROWS} — в {title('ca_log')}")
    lines += [f"ℹ️ {name(r)} — у источника запрет копирования: медиа копируются только с фильтром "
              "RestrictSavingContentBypassFilter" for r in notes[:REPORT_ROWS]]
    return "\n".join(lines)


@view("ca")
@view("rs")
@view("sp")
@view("ag")
@view("cc")
async def task_view(message: Message, edit: bool, nav: NavCB, state: FSMContext, sysd: Systemd,
                    runtime: Runtime, note: str = "", **_) -> None:
    project = status.find(nav.p)
    if project is None:
        await message.answer(texts.NO_PROJECT)
        return
    await show_task(message, edit, project, nav.s, sysd, runtime, note)


async def show_task(message: Message, edit: bool, project: Project, task: str, sysd: Systemd,
                    runtime: Runtime, note: str = "") -> None:
    st = await status.unit_state(sysd, project.task_unit)
    body = f"{ABOUT[task]}\n\nПоследний запуск: {_last_text(runtime, project, task, st)}"
    if task == "ca":
        body += "\n\n" + access_text(project)
    if not sysd.available:
        body += "\n\n" + texts.SYSTEMD_UNAVAILABLE
    own, hints = [], []
    if task == "sp":
        flags, opts = runtime.flags(project.key), runtime.opts(project.key)
        own = [[button(f"{'☑️' if f in flags else '⬜'} {label}", ActCB(a="sp_flag", p=project.key, i=n))]
               for n, (f, label) in enumerate(SP_FLAGS.items())]
        only = opts.get("only", ())
        own += [[button(f"📏 Лимит: {opts.get('max_pins', SP_DEFAULT_MAX_PINS)}", ActCB(a="sp_max", p=project.key)),
                 button(f"📍 Доноры: {len(only) if only else 'все'}", ActCB(a="sp_only", p=project.key))]]
        hints = [("☑️ / ⬜", "флаги запуска; проверка и выполнение — с одними и теми же"),
                 ("📏 Лимит", "сколько закрепов читать в чате или теме"),
                 ("📍 Доноры", "только эти доноры вместо всех")]
        if only:
            body += "\n\nТолько доноры: " + texts.refs(only)
    hidden = () if can_run_real(task, project, runtime, st) else (f"{task}_run",)
    await show(message, edit, task, project, body=body, note=note, own=own, own_hints=hints, hidden=hidden)


@on_action(router, "sp_flag")
async def on_flag(callback: CallbackQuery, callback_data: ActCB, sysd: Systemd, runtime: Runtime) -> None:
    project = await project_of(callback, callback_data.p)
    if project is None:
        return
    if 0 <= callback_data.i < len(settings.SYNC_PINS_FLAGS):
        runtime.flags(project.key).symmetric_difference_update({settings.SYNC_PINS_FLAGS[callback_data.i]})
    await callback.answer()
    await show_task(message_of(callback), True, project, "sp", sysd, runtime)


SP_DEFAULT_MAX_PINS = 100  # skylon_set/sync_pins.py --max-pins default
SP_ASKS = {
    "sp_max": "пришлите, сколько закрепов читать в одном чате или теме ({low}–{high}; по умолчанию "
              f"{SP_DEFAULT_MAX_PINS}), или <code>-</code>, чтобы вернуть значение по умолчанию.",
    "sp_only": "пришлите ID доноров через запятую или с новой строки — закрепы перенесутся только у "
               "них — или <code>-</code>, чтобы снова переносить у всех.",
}


def donors_of(project: Project) -> set:
    """The project's sources (and its broadcast channel) — what --only may name."""
    data = status.project_info(project).data
    ids = {configstore.chat_of(configstore.ref_str(r)) for d in configstore.directions(data) for r in d.get("from") or []}
    if isinstance(data.get("broadcast_channel"), int):
        ids.add(data["broadcast_channel"])
    return ids


@on_action(router, "sp_max", "sp_only")
async def on_option(callback: CallbackQuery, callback_data: ActCB, state: FSMContext, runtime: Runtime) -> None:
    project = await project_of(callback, callback_data.p)
    if project is None:
        return
    opts = runtime.opts(project.key)
    if callback_data.a == "sp_max":
        current = str(opts.get("max_pins", SP_DEFAULT_MAX_PINS))
        label = "📏 Лимит закрепов"
    else:
        current = texts.refs(opts["only"]) if opts.get("only") else "все"
        label = "📍 Доноры"
    low, high = settings.SYNC_PINS_MAX_PINS
    await start_form(
        callback, state, Input.value,
        f"{head(label)} — сейчас: {current}.\n\n{SP_ASKS[callback_data.a].format(low=low, high=high)}",
        NavCB(s="sp", p=project.key), data={"kind": callback_data.a, "p": project.key},
    )


@input_kind("sp_max")
@input_kind("sp_only")
async def set_option(message: Message, state: FSMContext, raw: str, data: dict, sysd: Systemd,
                     runtime: Runtime, **_) -> None:
    project = status.find(data["p"])
    if project is None:
        await leave_form(message.chat.id, state)
        await message.answer(texts.NO_PROJECT)
        return
    opts = runtime.opts(project.key)
    try:
        if raw == configstore.CLEAR:
            opts.pop("max_pins" if data["kind"] == "sp_max" else "only", None)
        elif data["kind"] == "sp_max":
            low, high = settings.SYNC_PINS_MAX_PINS
            if not raw.isdigit() or not low <= int(raw) <= high:
                raise ConfigError("bad_number", raw)
            opts["max_pins"] = int(raw)
        else:
            donors = [configstore.chat_of(r) for r in configstore.parse_chat_refs(raw)]
            if unknown := [d for d in donors if d not in donors_of(project)]:
                await message.answer(f"⚠️ Это не источники проекта: {texts.refs(unknown)}\nПришлите ещё раз:")
                return
            opts["only"] = tuple(dict.fromkeys(donors))
    except ConfigError as e:
        await message.answer(f"{texts.config_error(e.code, e.detail)}\nПришлите ещё раз:")
        return
    await leave_form(message.chat.id, state)
    await show_task(message, False, project, "sp", sysd, runtime, "✅ Запомнено. Перед выполнением — новая проверка.")


RUNNING = "⛔ Задача обслуживания этого проекта уже выполняется."
NEED_CHECK = "⛔ Сначала выполните проверку с теми же флагами и конфигурацией и дождитесь её успеха."


@on_action(router, "ca_dry", "rs_dry", "rs_run", "sp_dry", "sp_run", "ag_dry", "ag_run", "cc_dry", "cc_run")
async def on_run(callback: CallbackQuery, callback_data: ActCB, state: FSMContext, sysd: Systemd,
                 runtime: Runtime) -> None:
    project = await project_of(callback, callback_data.p)
    if project is None:
        return
    task, mode = callback_data.a.split("_")
    dry = mode == "dry"
    if not sysd.available:
        await stale_tap(callback, texts.SYSTEMD_UNAVAILABLE)
        return
    if not await session_ok(callback, project):
        return
    st = await status.unit_state(sysd, project.task_unit)
    if st is not None and st.running:
        await stale_tap(callback, RUNNING)
        return
    if not dry and not can_run_real(task, project, runtime, st):
        await stale_tap(callback, NEED_CHECK)
        return
    holders = [(p, u) for p, u in await status.session_holders(sysd, project) if u != project.task_unit]
    if dry:
        what = "Проверка ничего не меняет — только выводит план."
    elif task == "cc":
        what = "⚠️ Все сообщения в каналах-получателях проекта будут удалены. Это необратимо."
    else:
        what = "⚠️ Будут внесены изменения в каналы."
    await ask_confirm(
        callback, state,
        f"{head(SCREENS[task].title)}: {'проверка' if dry else 'выполнение'}?\n\n{what}{pause_text(holders)}",
        "task", NavCB(s=task, p=project.key), yes=YES_DELETE if task == "cc" and not dry else YES,
        p=project.key, task=task, dry=dry,
    )


@confirmed("task")
async def do_run(callback: CallbackQuery, action: dict, state: FSMContext, sysd: Systemd,
                 runtime: Runtime, **_) -> None:
    project = await project_of(callback, action["p"])
    if project is None:
        return
    task, dry = action["task"], action["dry"]
    if left := runtime.cooldown_left(project.task_unit):
        await stale_tap(callback, texts.COOLDOWN.format(sec=left))
        return
    # Again: the unit may have started, or the flags changed, since the question.
    st = await status.unit_state(sysd, project.task_unit)
    if st is not None and st.running:
        await stale_tap(callback, RUNNING)
        return
    if not dry and not can_run_real(task, project, runtime, st):
        await stale_tap(callback, NEED_CHECK)
        return
    args = _args(task, dry, project, runtime)
    try:
        settings.TASK_ENV_DIR.mkdir(parents=True, exist_ok=True)
        (settings.TASK_ENV_DIR / f"{project.key}.env").write_text(env_file_text(task, args), encoding="utf-8")
        await turns.start(sysd, runtime, project, project.task_unit)
    except (OSError, SystemdError) as e:
        logger.error("panel: launching %s failed: %s", project.task_unit, e)
        await stale_tap(callback, texts.SYSTEMD_ERROR.format(detail=str(e)[:150]))
        return
    runtime.launches[(project.key, task)] = Launch(tuple(args), dry, time.time(), config_sha(project))
    logger.info("panel: started %s %s %s", project.task_unit, task, args)
    await callback.answer("Задача запущена.")
    await show_task(message_of(callback), True, project, task, sysd, runtime,
                    f"▶️ {'Проверка' if dry else 'Выполнение'} запущено. Ход и вывод — {title(task + '_log')}.")


@on_action(router, "ca_log", "rs_log", "sp_log", "ag_log", "cc_log")
async def on_log(callback: CallbackQuery, callback_data: ActCB, sysd: Systemd) -> None:
    project = await project_of(callback, callback_data.p)
    if project is None:
        return
    await callback.answer()
    await show_unit(message_of(callback), True, project, 2, sysd)
