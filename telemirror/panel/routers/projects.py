"""📁 Проекты: the list, a project's card (its mirror: ▶️ / ⏹ / 🔁), ➕ Новый
проект, 🧰 Управление (name, icon, account, deletion)."""

import logging
import os
import unicodedata
from contextlib import suppress
from typing import Optional

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from telemirror import projects
from telemirror.panel import registry, settings, status, texts, turns
from telemirror.panel.callbacks import ActCB, ChoiceCB, NavCB
from telemirror.panel.keyboards.common import button, choice_kb, pages, paged_rows
from telemirror.panel.registry import YES_DELETE, title
from telemirror.panel.routers import accounts
from telemirror.panel.routers._common import (
    ask,
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
from telemirror.panel.runtime import Runtime
from telemirror.panel.screens import esc, head, project_label, show, view
from telemirror.panel.states import Input, NewProject
from telemirror.panel.systemd import Systemd, SystemdError
from telemirror.panel.watcher import unit_label
from telemirror.projects import Project

logger = logging.getLogger(__name__)
router = Router(name="projects")

NAME_MAX = 40
ICONS = ("🪞", "📰", "🏰", "🚀", "💎", "🦊", "⭐️", "🔥")


# ── 📁 Проекты ──────────────────────────────────────────────────────────────


@view("prj")
async def projects_view(message: Message, edit: bool, nav: NavCB, state: FSMContext, sysd: Systemd,
                        note: str = "", **_) -> None:
    found = projects.list_projects()
    items = []
    for p in found:
        st = await status.unit_state(sysd, p.live_unit)
        info = status.project_info(p)
        count = len(info.directions) if info.readable else texts.UNKNOWN
        items.append(button(
            f"{p.icon} {p.name} · {texts.state_icon(st.active if st else None)} · {count} напр.",
            NavCB(s="card", p=p.key),
        ))
    body = (
        f"Проектов: <b>{len(found)}</b>. 🟢 — зеркало работает, ⚪️ — остановлено, 🔴 — сбой."
        if found else "Проектов пока нет. Создайте первый: ➕ Новый проект."
    )
    own = paged_rows(items, nav.pg, settings.PAGE_SIZE, lambda pg: NavCB(s="prj", pg=pg))
    await show(message, edit, "prj", body=body, note=note, own=own,
               pg=nav.pg % pages(len(items), settings.PAGE_SIZE))


# ── 📁 Проект ───────────────────────────────────────────────────────────────


@view("card")
async def card_view(message: Message, edit: bool, nav: NavCB, state: FSMContext, sysd: Systemd,
                    note: str = "", **_) -> None:
    project = status.find(nav.p)
    if project is None:
        await projects_view(message, edit, NavCB(s="prj"), state, sysd, note=texts.NO_PROJECT)
        return
    await show_card(message, edit, project, sysd, note)


async def show_card(message: Message, edit: bool, project: Project, sysd: Systemd, note: str = "") -> None:
    info = status.project_info(project)
    st = await status.unit_state(sysd, project.live_unit)
    active = st.active if st else None
    lines = [
        f"👤 Аккаунт: {esc(accounts.account_label(project.session))}"
        + ("" if project.session_path.exists() else f"\n{texts.SESSION_MISSING}"),
        f"{texts.state_icon(active)} Зеркало: <b>{texts.mirror_state(active)}</b>"
        + (f" · с {texts.fmt_ts(st.since)}" if st and st.since and st.running else ""),
        f"🔀 Направлений: <b>{len(info.directions) if info.readable else texts.UNKNOWN}</b>",
        f"🗂 Конфиг: <code>{esc(project.config)}</code>",
    ]
    shared = projects.sharing_session(project)
    if shared:
        lines.append("🔁 На этой же сессии: " + ", ".join(esc(project_label(p)) for p in shared)
                     + " — работают по очереди.")
    if info.read_only:
        lines.append(texts.READ_ONLY[info.read_only])
    if info.error:
        lines.append(f"⚠️ Не удалось прочитать конфиг: <code>{esc(info.error[:300])}</code>")
    if info.snapshot and st and st.running and st.since and info.snapshot.mtime > st.since:
        lines.append("⚠️ <b>Есть неприменённые изменения</b> — нажмите «🔁 Перезапустить».")
    if not sysd.available:
        lines.append(texts.SYSTEMD_UNAVAILABLE)
    running = bool(st and st.running)
    hidden = ("start",) if running else ("stop", "restart")
    await show(message, edit, "card", project, body="\n".join(lines), note=note, hidden=hidden)


async def _systemd_ready(callback: CallbackQuery, sysd: Systemd) -> bool:
    if not sysd.available:
        await stale_tap(callback, texts.SYSTEMD_UNAVAILABLE)
        return False
    return True


def pause_text(holders: list, mirror: bool = False) -> str:
    """What starting will stop, for a confirmation ("" — nothing): ``mirror``
    — a mirror replaces them (turned off), else they're paused for a run."""
    if not holders:
        return ""
    names = "\n".join(f"• {esc(unit_label(p, u))}" for p, u in holders)
    after = (
        "Это будет выключено: на одной сессии работает одно зеркало."
        if mirror else "Это будет остановлено; зеркала запустятся снова, когда это закончится."
    )
    return f"\n\nНа этой сессии сейчас работает:\n{names}\n{after}"


async def restart_pause_text(sysd: Systemd, project: Project) -> str:
    """For a restart's confirmation: what else runs on the mirror's session —
    possible after 👤 Аккаунт moved the project to a busy session; the restart
    turns it off (``turns.start``) instead of crash-looping on the session lock."""
    holders = [(p, u) for p, u in await status.session_holders(sysd, project) if u != project.live_unit]
    return pause_text(holders, mirror=True)


async def start_unit(callback: CallbackQuery, state: FSMContext, sysd: Systemd, runtime: Runtime,
                     project: Project, unit: str, kind: str, back: NavCB, what: str) -> bool:
    """Start now, or ask first when it pauses something on the session.
    False: refused (said in a pop-up)."""
    left = runtime.cooldown_left(unit)
    if left:
        await stale_tap(callback, texts.COOLDOWN.format(sec=left))
        return False
    holders = [(p, u) for p, u in await status.session_holders(sysd, project) if u != unit]
    if holders:
        await ask_confirm(callback, state, f"{head(what)}?{pause_text(holders, unit == project.live_unit)}",
                          kind, back, p=project.key, unit=unit)
        return False
    await do_start(callback, sysd, runtime, project, unit)
    return True


async def do_start(callback: CallbackQuery, sysd: Systemd, runtime: Runtime, project: Project, unit: str) -> bool:
    try:
        await turns.start(sysd, runtime, project, unit)
    except SystemdError as e:
        logger.error("panel: starting %s failed: %s", unit, e)
        await stale_tap(callback, texts.SYSTEMD_ERROR.format(detail=str(e)[:150]))
        return False
    await callback.answer("Команда отправлена systemd.")
    return True


@on_action(router, "start")
async def on_start(callback: CallbackQuery, callback_data: ActCB, state: FSMContext, sysd: Systemd,
                   runtime: Runtime) -> None:
    project = await project_of(callback, callback_data.p)
    if project is None or not await _systemd_ready(callback, sysd) or not await session_ok(callback, project):
        return
    info = status.project_info(project)
    if info.read_only == "missing":  # config.py refuses to start without it
        await stale_tap(callback, texts.READ_ONLY["missing"])
        return
    if info.readable and not info.directions:
        await stale_tap(callback, "⛔ В проекте нет направлений. Добавьте: "
                        f"{registry.menu_path('dir_add')}.")
        return
    if await start_unit(callback, state, sysd, runtime, project, project.live_unit, "start",
                        NavCB(s="card", p=project.key), "▶️ Запустить зеркало"):
        await show_card(message_of(callback), True, project, sysd, "▶️ Зеркало запускается.")


@confirmed("start")
async def do_confirmed_start(callback: CallbackQuery, action: dict, state: FSMContext, sysd: Systemd,
                             runtime: Runtime, **_) -> None:
    project = await project_of(callback, action["p"])
    if project is not None and await do_start(callback, sysd, runtime, project, action["unit"]):
        await show_card(message_of(callback), True, project, sysd, "▶️ Запущено.")


@on_action(router, "stop", "restart")
async def on_stop(callback: CallbackQuery, callback_data: ActCB, state: FSMContext, sysd: Systemd) -> None:
    project = await project_of(callback, callback_data.p)
    if project is None or not await _systemd_ready(callback, sysd):
        return
    text = (
        f"{head('⏹ Остановить зеркало')} {esc(project_label(project))}?\n\nПересылка прекратится до "
        "запуска. Ежедневный перезапуск в 04:00 остановленное зеркало не поднимает."
        if callback_data.a == "stop" else
        f"{head('🔁 Перезапустить зеркало')} {esc(project_label(project))}?\n\nКонфигурация будет "
        "перечитана; на время перезапуска пересылка приостанавливается."
        + await restart_pause_text(sysd, project)
    )
    await ask_confirm(callback, state, text, callback_data.a, NavCB(s="card", p=project.key), p=project.key)


@confirmed("stop")
@confirmed("restart")
async def do_stop(callback: CallbackQuery, action: dict, state: FSMContext, sysd: Systemd,
                  runtime: Runtime, **_) -> None:
    project = await project_of(callback, action["p"])
    if project is None:
        return
    restart = action["kind"] == "restart"
    if restart and runtime.cooldown_left(project.live_unit):
        await stale_tap(callback, texts.COOLDOWN.format(sec=runtime.cooldown_left(project.live_unit)))
        return
    try:
        if restart:
            await turns.start(sysd, runtime, project, project.live_unit, restart=True)
        else:
            await sysd.disable(project.live_unit)
    except SystemdError as e:
        await stale_tap(callback, texts.SYSTEMD_ERROR.format(detail=str(e)[:150]))
        return
    await callback.answer("Команда отправлена systemd.")
    await show_card(message_of(callback), True, project, sysd,
                    "🔁 Зеркало перезапускается." if restart else "⏹ Зеркало остановлено.")


# ── ➕ Новый проект: name → icon → account ───────────────────────────────────

NAME_ASK = f"{head(title('new'))} — пришлите имя проекта (до {NAME_MAX} символов):"
ICON_ASK = "— выберите значок проекта или пришлите свой эмодзи:"


def name_problem(name: str, skip: str = "") -> Optional[str]:
    if not name or len(name) > NAME_MAX:
        return f"нужно от 1 до {NAME_MAX} символов"
    if any(p.name.casefold() == name.casefold() and p.key != skip for p in projects.list_projects()):
        return "проект с таким именем уже есть"
    return None


def icon_problem(icon: str) -> Optional[str]:
    if not icon or len(icon) > 8 or any(unicodedata.category(c)[0] in "LN" for c in icon):
        return "нужен один эмодзи"
    if registry.emoji_of(icon) in {registry.emoji_of(s.title) for s in registry.SCREENS.values()}:
        return "этот значок уже означает раздел бота — выберите другой"
    return None


def icon_kb():
    return choice_kb("icon", [(i, i) for i in ICONS], widths=(4,))


@on_action(router, "new")
async def on_new(callback: CallbackQuery, state: FSMContext) -> None:
    await start_form(callback, state, NewProject.name, NAME_ASK, NavCB(s="prj"))


@router.message(NewProject.name)
async def on_new_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if problem := name_problem(name):
        await message.answer(f"Не подходит: {problem}. Пришлите другое имя:")
        return
    await ask(message, state, NewProject.icon, f"{head(title('new'))} «{esc(name)}» {ICON_ASK}",
              icon_kb(), name=name)


async def _new_icon(message: Message, state: FSMContext, icon: str) -> None:
    paths = accounts.session_files()
    await ask(
        message, state, NewProject.account,
        f"{head(title('new'))} {esc(icon)} «{esc((await state.get_data())['name'])}» — выберите аккаунт: "
        "от его имени зеркало будет читать источники и писать в получатели. Проекты на одной "
        "сессии работают по очереди.",
        accounts.picker(paths), icon=icon, accounts=paths, then="new",
    )


@router.message(NewProject.icon)
async def on_new_icon_typed(message: Message, state: FSMContext) -> None:
    icon = (message.text or "").strip()
    if problem := icon_problem(icon):
        await message.answer(f"Не подходит: {problem}. Выберите значок выше или пришлите другой:")
        return
    await _new_icon(message, state, icon)


@router.callback_query(ChoiceCB.filter(F.scope == "icon"))
async def on_icon_button(callback: CallbackQuery, callback_data: ChoiceCB, state: FSMContext, **deps) -> None:
    current = await state.get_state()
    if callback_data.value not in ICONS or current not in (NewProject.icon.state, Input.value.state):
        await stale_tap(callback)
        return
    await callback.answer()
    with suppress(Exception):
        await message_of(callback).edit_reply_markup(reply_markup=None)
    if current == NewProject.icon.state:
        await _new_icon(message_of(callback), state, callback_data.value)
    else:
        await set_icon(message_of(callback), state, callback_data.value, await state.get_data(), **deps)


async def create(message: Message, name: str, icon: str, session: str, note: str, sysd: Systemd) -> None:
    """The new project (an account was picked or signed in): its card."""
    project = projects.create_project(name, icon, session)
    logger.info("panel: project %s created on %s", project.key, session)
    done = (f"{note}\n" if note else "") + (
        f"✅ Проект {esc(project_label(project))} создан. Теперь добавьте направления: "
        f"{registry.SCREENS['dirs'].title} → {title('dir_add')}."
    )
    await show_card(message, False, project, sysd, done)


# ── 🧰 Управление ───────────────────────────────────────────────────────────


@on_action(router, "rename")
async def on_rename(callback: CallbackQuery, callback_data: ActCB, state: FSMContext) -> None:
    project = await project_of(callback, callback_data.p)
    if project is None:
        return
    await start_form(callback, state, Input.value,
                     f"{head(title('rename'))} — сейчас «{esc(project.name)}». Пришлите новое имя:",
                     NavCB(s="mng", p=project.key), data={"kind": "rename", "p": project.key})


@input_kind("rename")
async def set_name(message: Message, state: FSMContext, raw: str, data: dict, sysd: Systemd, **_) -> None:
    if problem := name_problem(raw, skip=data["p"]):
        await message.answer(f"Не подходит: {problem}. Пришлите другое имя:")
        return
    await leave_form(message.chat.id, state)
    project = projects.update_project(data["p"], name=raw)
    await show(message, False, "mng", project, note=f"✅ Проект переименован: {esc(project_label(project))}.")


@on_action(router, "icon")
async def on_icon(callback: CallbackQuery, callback_data: ActCB, state: FSMContext) -> None:
    project = await project_of(callback, callback_data.p)
    if project is None:
        return
    await start_form(callback, state, Input.value, f"{head(title('icon'))} {ICON_ASK}",
                     NavCB(s="mng", p=project.key), markup=icon_kb(), data={"kind": "icon", "p": project.key})


@input_kind("icon")
async def set_icon(message: Message, state: FSMContext, raw: str, data: dict, **_) -> None:
    if problem := icon_problem(raw):
        await message.answer(f"Не подходит: {problem}. Выберите значок выше или пришлите другой:")
        return
    await leave_form(message.chat.id, state)
    project = projects.update_project(data["p"], icon=raw)
    await show(message, False, "mng", project, note=f"✅ Новый значок: {esc(project_label(project))}.")


@on_action(router, "account")
async def on_account(callback: CallbackQuery, callback_data: ActCB, state: FSMContext) -> None:
    project = await project_of(callback, callback_data.p)
    if project is None:
        return
    paths = accounts.session_files()
    await start_form(
        callback, state, Input.value,
        f"{head(title('account'))} — сейчас {esc(accounts.account_label(project.session))}. "
        "Выберите другой; зеркало начнёт работать от него после перезапуска.",
        NavCB(s="mng", p=project.key), markup=accounts.picker(paths),
        data={"kind": "account", "p": project.key, "accounts": paths, "then": project.key},
    )


@input_kind("account")
async def account_typed(message: Message, state: FSMContext, raw: str, data: dict, **_) -> None:
    await message.answer("Выберите аккаунт кнопкой выше — или /cancel, чтобы выйти.")


async def set_account(message: Message, key: str, session: str, note: str = "") -> None:
    project = status.find(key)
    if project is None:
        await message.answer(texts.NO_PROJECT)
        return
    project = projects.update_project(key, session=session)
    done = (f"{note}\n" if note else "") + (
        f"✅ Аккаунт проекта: {esc(accounts.account_label(session))}. "
        "Перезапустите зеркало, чтобы он заработал."
    )
    await show(message, False, "mng", project, note=done)


@view("mng")
async def manage_view(message: Message, edit: bool, nav: NavCB, state: FSMContext, sysd: Systemd,
                      note: str = "", **_) -> None:
    project = status.find(nav.p)
    if project is None:
        await projects_view(message, edit, NavCB(s="prj"), state, sysd, note=texts.NO_PROJECT)
        return
    body = (f"Имя: <b>{esc(project.name)}</b> · значок: {esc(project.icon)} · ключ <code>{esc(project.key)}</code>\n"
            f"👤 Аккаунт: {esc(accounts.account_label(project.session))}")
    await show(message, edit, "mng", project, body=body, note=note)


@on_action(router, "delete")
async def on_delete(callback: CallbackQuery, callback_data: ActCB, state: FSMContext) -> None:
    project = await project_of(callback, callback_data.p)
    if project is None:
        return
    own_config = project.config_path.resolve().is_relative_to((projects.PROJECTS_DIR / project.key).resolve())
    keeps = ("Папка проекта вместе с конфигом перенесётся в <code>projects/.deleted/</code> — "
             "оттуда её можно вернуть." if own_config else
             f"Файл конфигурации <code>{esc(project.config)}</code> останется на месте, настройки "
             "проекта перенесутся в <code>projects/.deleted/</code>.")
    await ask_confirm(
        callback, state,
        f"{head(title('delete'))} {esc(project_label(project))}?\n\nЕго зеркало, догрузка и "
        f"обслуживание будут остановлены. {keeps} Сессия аккаунта останется в {registry.ACCOUNTS}.",
        "delete", NavCB(s="mng", p=project.key), yes=YES_DELETE, p=project.key,
    )


@confirmed("delete")
async def do_delete(callback: CallbackQuery, action: dict, state: FSMContext, sysd: Systemd, **_) -> None:
    project = await project_of(callback, action["p"])
    if project is None:
        return
    if sysd.available:
        for unit in project.units:  # disabled too: an enabled instance would fail on every boot
            with suppress(SystemdError):
                await sysd.disable(unit)
    archive = projects.delete_project(project.key)
    logger.info("panel: project %s deleted, archived to %s", project.key, archive)
    await callback.answer()
    where = os.path.relpath(archive, projects.REPO_DIR)
    await projects_view(message_of(callback), True, NavCB(s="prj"), state, sysd,
                        note=f"✅ Проект {esc(project_label(project))} удалён. Копия: <code>{esc(where)}</code>.")


@router.message(NewProject.account)
async def on_new_account_typed(message: Message, state: FSMContext) -> None:
    await message.answer("Выберите аккаунт кнопкой выше — или /cancel, чтобы выйти.")

