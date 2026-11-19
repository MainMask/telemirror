"""📁 Проекты: the list, a project's card (its mirror: ▶️ / ⏹ / 🔁), ➕ Новый
проект, the project's part of ⚙️ Настройки проекта (name, icon, account,
deletion; the screen itself: routers/params.py)."""

import logging
import os
import unicodedata
from contextlib import suppress
from typing import Optional

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import registry, settings, status, texts
from bot.callbacks import ActCB, ChoiceCB, NavCB
from bot.keyboards.common import button, choice_kb, paged_rows, pages
from bot.registry import YES_DELETE, title
from bot.routers import _units
from bot.routers._common import (
    ask,
    ask_confirm,
    confirmed,
    input_kind,
    message_of,
    on_action,
    stale_tap,
    start_form,
)
from bot.runtime import Runtime
from bot.screens import open_screen, show, view
from bot.sessions import account_label, picker, session_files
from bot.states import Input, NewProject, leave_form
from bot.systemd import Systemd, SystemdError
from bot.texts import esc, head, project_label
from telemirror import projects
from telemirror.projects import Project

logger = logging.getLogger(__name__)
router = Router(name="projects")

ICONS = ("🪞", "📰", "🏰", "🚀", "💎", "🦊", "⭐️", "🔥")


# ── 📁 Проекты ──────────────────────────────────────────────────────────────


@view("prj")
async def projects_view(message: Message, edit: bool, nav: NavCB, *, sysd: Systemd, note: str = "",
                        **_) -> None:
    found = projects.list_projects()
    page = nav.pg % pages(len(found), settings.PAGE_SIZE)
    items = []
    for p in found:
        st = await status.unit_state(sysd, p.live_unit)
        info = status.project_info(p)
        count = len(info.directions) if info.readable else texts.UNKNOWN
        active = st.active if st else None
        items.append(button(
            f"{project_label(p)} · {texts.state_icon(active)} {texts.mirror_state(active)} · направлений: {count}",
            NavCB(s="card", p=p.key, pg=page),
        ))
    about = "Проект — это одно зеркало: из каких каналов в какие копировать посты и от имени какого аккаунта."
    # the first time it is said, later folded
    body = f"Проектов: <b>{len(found)}</b>." if found else f"Проектов пока нет. {about} Создайте первый: {title('new')}."
    own = paged_rows(items, page, settings.PAGE_SIZE, lambda pg: NavCB(s="prj", pg=pg))
    await show(message, edit, "prj", body=body, more=about if found else "", note=note, own=own, pg=page)


# ── 📁 Проект ───────────────────────────────────────────────────────────────


@view("card")
async def card_view(message: Message, edit: bool, nav: NavCB, *, project: Project, sysd: Systemd,
                    note: str = "", **_) -> None:
    info = status.project_info(project)
    st = await status.unit_state(sysd, project.live_unit)
    active = st.active if st else None
    running = bool(st and st.running)
    pending = bool(info.snapshot and running and st and st.since and info.snapshot.mtime > st.since)
    lines = [
        f"{texts.state_icon(active)} Копирование: <b>{texts.mirror_state(active)}</b>"
        + (f" · с {texts.fmt_ts(st.since)}" if st and st.since and running else ""),
        f"👤 Аккаунт: {esc(account_label(project.session))}"
        + ("" if project.session_path.exists() else f"\n{texts.SESSION_MISSING}"),
        f"🔀 Направлений: <b>{len(info.directions) if info.readable else texts.UNKNOWN}</b>",
    ]
    if shared := projects.sharing_session(project):
        lines.append("👤 Этот же аккаунт у проектов: " + ", ".join(esc(project_label(p)) for p in shared)
                     + " — они работают по очереди, не одновременно.")
    if not info.readable:
        lines.append(texts.unreadable(info))
    if pending:
        lines.append(f"⚠️ <b>Изменения ещё не применены</b> — нажмите «{title('restart')}».")
    elif step := next_step(project, info, running):
        lines.append(f"👉 <b>Что дальше:</b> {step}")
    if not sysd.available:
        lines.append(texts.SYSTEMD_UNAVAILABLE)
    hidden = ("start",) if st and st.running else ("stop", "restart")
    ready = project.session_path.exists() and info.readable and bool(info.directions)
    primary = "restart" if pending else ("start" if not running and ready else "")
    await show(message, edit, "card", project, body="\n".join(lines), note=note, hidden=hidden, pg=nav.pg,
               primary=primary)


def next_step(project: Project, info: status.ProjectInfo, running: bool) -> str:
    """What a new project still needs, in the order of the work; "" when it runs."""
    if not project.session_path.exists():
        return f"выберите аккаунт: {esc(registry.menu_path('account'))}."
    if info.readable and not info.directions:
        return f"добавьте, откуда и куда копировать: {esc(registry.menu_path('dir_add'))}."
    if not running and info.readable:
        return f"нажмите «{title('start')}» — и новые посты начнут копироваться."
    return ""


def _card(project: Project, cb: ActCB) -> NavCB:
    return NavCB(s="card", p=project.key, pg=cb.pg)


@on_action(router, "start")
async def on_start(callback: CallbackQuery, callback_data: ActCB, project: Project, state: FSMContext,
                   sysd: Systemd, runtime: Runtime, deps: dict) -> None:
    if not await _units.can_start(callback, sysd, runtime, project, project.live_unit):
        return
    info = status.project_info(project)
    if info.missing:  # telemirror.config refuses to start without it
        await stale_tap(callback, texts.CONFIG_MISSING)
        return
    if info.readable and not info.directions:
        await stale_tap(callback, f"⛔ В проекте нет направлений. Добавьте: {registry.menu_path('dir_add')}.")
        return
    back = _card(project, callback_data)
    if await _units.ask_start(callback, state, sysd, project, project.live_unit,
                              f"{head(title('start'))} {esc(project_label(project))}?", back) \
            and await _units.launch(callback, sysd, runtime, project, project.live_unit):
        await open_screen(back, message_of(callback), True, deps, note=_units.STARTING)


@on_action(router, "stop", "restart")
async def on_stop(callback: CallbackQuery, callback_data: ActCB, project: Project, state: FSMContext,
                  sysd: Systemd) -> None:
    await _units.ask_stop(callback, state, sysd, project, project.live_unit, callback_data.a == "restart",
                          _card(project, callback_data))


# ── ➕ Новый проект: name → icon → account ───────────────────────────────────

NAME_ASK = f"{head(title('new'))} — пришлите имя проекта (до {settings.PROJECT_NAME_MAX} символов):"
ICON_ASK = "— выберите значок проекта или пришлите свой эмодзи:"


def name_problem(name: str, skip: str = "") -> Optional[str]:
    if not name or len(name) > settings.PROJECT_NAME_MAX:
        return f"нужно от 1 до {settings.PROJECT_NAME_MAX} символов"
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
    paths = session_files()
    await ask(
        message, state, NewProject.account,
        f"{head(title('new'))} {esc(icon)} «{esc((await state.get_data())['name'])}» — выберите аккаунт: "
        "от его имени зеркало будет читать каналы-источники и публиковать в ваших каналах. Проекты "
        "с одним аккаунтом работают по очереди.",
        picker(paths), icon=icon, accounts=paths, then="new",
    )


@router.message(NewProject.icon)
async def on_new_icon_typed(message: Message, state: FSMContext) -> None:
    icon = (message.text or "").strip()
    if problem := icon_problem(icon):
        await message.answer(f"Не подходит: {problem}. Выберите значок выше или пришлите другой:")
        return
    await _new_icon(message, state, icon)


@router.callback_query(StateFilter(NewProject.icon, Input.value), ChoiceCB.filter(F.scope == "icon"))
async def on_icon_button(callback: CallbackQuery, callback_data: ChoiceCB, state: FSMContext) -> None:
    data = await state.get_data()
    in_manage = await state.get_state() == Input.value.state
    if callback_data.value not in ICONS or (in_manage and data.get("kind") != "icon"):
        await stale_tap(callback)
        return
    await callback.answer()
    await message_of(callback).edit_reply_markup(reply_markup=None)
    if in_manage:
        await _set_icon(message_of(callback), state, data["p"], callback_data.value)
    else:
        await _new_icon(message_of(callback), state, callback_data.value)


@router.message(NewProject.account)
async def on_new_account_typed(message: Message) -> None:
    await message.answer(texts.USE_BUTTONS)


# ── ⚙️ Настройки проекта: name, icon, account, deletion ──────────────────────


def _manage(project: Project) -> NavCB:
    return NavCB(s="mng", p=project.key)


@on_action(router, "rename")
async def on_rename(callback: CallbackQuery, project: Project, state: FSMContext) -> None:
    await start_form(callback, state, Input.value,
                     f"{head(title('rename'))} — сейчас «{esc(project.name)}». Пришлите новое имя:",
                     _manage(project), data={"kind": "rename", "p": project.key})


@input_kind("rename")
async def set_name(message: Message, state: FSMContext, raw: str, data: dict, project: Project, deps: dict,
                   **_) -> None:
    if problem := name_problem(raw, skip=project.key):
        await message.answer(f"Не подходит: {problem}. Пришлите другое имя:")
        return
    await leave_form(message.chat.id, state)
    project = projects.update_project(project.key, name=raw)
    await open_screen(_manage(project), message, False, deps,
                      note=f"✅ Проект переименован: {esc(project_label(project))}.")


@on_action(router, "icon")
async def on_icon(callback: CallbackQuery, project: Project, state: FSMContext) -> None:
    await start_form(callback, state, Input.value, f"{head(title('icon'))} {ICON_ASK}",
                     _manage(project), markup=icon_kb(), data={"kind": "icon", "p": project.key})


@input_kind("icon")
async def set_icon(message: Message, state: FSMContext, raw: str, data: dict, project: Project, **_) -> None:
    if problem := icon_problem(raw):
        await message.answer(f"Не подходит: {problem}. Выберите значок выше или пришлите другой:")
        return
    await _set_icon(message, state, project.key, raw)


async def _set_icon(message: Message, state: FSMContext, key: str, icon: str) -> None:
    await leave_form(message.chat.id, state)
    project = projects.update_project(key, icon=icon)
    await open_screen(_manage(project), message, False, {}, note=f"✅ Новый значок: {esc(project_label(project))}.")


@on_action(router, "account")
async def on_account(callback: CallbackQuery, project: Project, state: FSMContext) -> None:
    paths = session_files()
    await start_form(
        callback, state, Input.value,
        f"{head(title('account'))} — сейчас {esc(account_label(project.session))}. "
        "Выберите другой; посты начнут копироваться от его имени после перезапуска.",
        _manage(project), markup=picker(paths), choice=True,
        data={"kind": "account", "p": project.key, "accounts": paths, "then": project.key},
    )


@input_kind("account")
async def account_typed(message: Message, **_) -> None:
    await message.answer(texts.USE_BUTTONS)


@on_action(router, "delete")
async def on_delete(callback: CallbackQuery, project: Project, state: FSMContext) -> None:
    own_config = project.config_path.resolve().is_relative_to((projects.PROJECTS_DIR / project.key).resolve())
    keeps = ("Проект вместе с файлом настроек перенесётся в архив <code>projects/.deleted/</code> — "
             "оттуда его можно вернуть вручную." if own_config else
             f"Файл настроек <code>{esc(project.config)}</code> останется на месте, сам проект "
             "перенесётся в архив <code>projects/.deleted/</code>.")
    await ask_confirm(
        callback, state,
        f"{head(title('delete'))} {esc(project_label(project))}?\n\nКопирование новых и старых постов и "
        f"инструменты проекта будут остановлены. Уже скопированные посты останутся. {keeps} "
        f"Аккаунт останется в {registry.ACCOUNTS}.",
        "delete", _manage(project), yes=YES_DELETE, p=project.key,
    )


@confirmed("delete")
async def do_delete(callback: CallbackQuery, action: dict, state: FSMContext, project: Project, sysd: Systemd,
                    runtime: Runtime, deps: dict, **_) -> None:
    if sysd.available:
        for unit in project.units:  # disabled too: an enabled instance would fail on every boot
            with suppress(SystemdError):
                await sysd.disable(unit)
    archive = projects.delete_project(project.key)
    runtime.forget(project)
    logger.info("panel: project %s deleted, archived to %s", project.key, archive)
    await callback.answer()
    where = os.path.relpath(archive, projects.REPO_DIR)
    await open_screen(NavCB(s="prj"), message_of(callback), True, deps,
                      note=f"✅ Проект {esc(project_label(project))} удалён. Копия: <code>{esc(where)}</code>.")
