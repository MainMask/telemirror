"""🔀 Направления: the list, one direction's card and its settings, ➕ Добавить."""

import logging
from contextlib import suppress
from typing import Any, Optional

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from telemirror.panel import configstore, settings, status, texts
from telemirror.panel.callbacks import ActCB, ChoiceCB, NavCB
from telemirror.panel.configstore import ConfigError, ConfigStore
from telemirror.panel.keyboards.common import button, choice_kb, pages, paged_rows
from telemirror.panel.registry import YES_DELETE, title
from telemirror.panel.routers._common import (
    ask,
    ask_confirm,
    confirmed,
    input_kind,
    leave_form,
    message_of,
    on_action,
    project_of,
    stale_tap,
    start_form,
)
from telemirror.panel.routers.replay import DEFAULT_REPLAY_DELAY
from telemirror.panel.screens import esc, head, show, view
from telemirror.panel.states import AddDirection, Input
from telemirror.panel.systemd import Systemd
from telemirror.panel.writes import save
from telemirror.projects import Project

logger = logging.getLogger(__name__)
router = Router(name="directions")

MODES = {"copy": "копия", "forward": "пересылка"}


def effective(d: Any, data: Any) -> tuple:
    """(mode, edits repeated, deletes repeated): the direction's own, else the project's."""
    mode = str(d.get("mode", data.get("mode", "copy")))
    edit_on = not bool(d.get("disable_edit", data.get("disable_edit", False)))
    delete_on = not bool(d.get("disable_delete", data.get("disable_delete", False)))
    return mode, edit_on, delete_on


def replay_delay_text(d: Any) -> str:
    pm = d.get("past_mode")
    delay = pm.get("send_delay") if isinstance(pm, dict) else None
    return f"по умолч. ({DEFAULT_REPLAY_DELAY} с)" if delay is None else f"{esc(delay)} с"


def direction(project: Project, index: int, fp: str = "") -> Optional[Any]:
    """The direction at ``index`` — None if gone, or changed when ``fp`` is given."""
    dirs = status.project_info(project).directions
    if not 0 <= index < len(dirs) or (fp and configstore.fingerprint(dirs[index]) != fp):
        return None
    return dirs[index]


# ── 🔀 Направления ──────────────────────────────────────────────────────────


@view("dirs")
async def directions_view(message: Message, edit: bool, nav: NavCB, state: FSMContext, note: str = "",
                          **_) -> None:
    project = status.find(nav.p)
    if project is None:
        await message.answer(texts.NO_PROJECT)
        return
    await show_directions(message, edit, project, nav.pg, note)


async def show_directions(message: Message, edit: bool, project: Project, page: int, note: str = "") -> None:
    info = status.project_info(project)
    dirs = info.directions
    count = pages(len(dirs), settings.PAGE_SIZE)
    page %= count
    items = []
    for n, d in enumerate(dirs):
        mode, edit_on, delete_on = effective(d, info.data)
        marks = "".join([
            " ↔️" if mode == "forward" else "",
            " 📜" if d.get("past_mode") else "",
            " 🧹" if d.get("filters") else "",
        ])
        label = f"{n + 1}. {texts.short_refs(list(d.get('from') or []))} → {texts.short_refs(list(d.get('to') or []))}"
        items.append(button(label + marks, NavCB(s="dir", p=project.key, i=n, pg=page)))
    if not info.readable:
        body = texts.READ_ONLY.get(info.read_only or "", "") or f"⚠️ <code>{esc(info.error or '')}</code>"
    elif dirs:
        body = (f"Всего: <b>{len(dirs)}</b> · стр. {page + 1}/{count}. "
                "Значки: ↔️ пересылка, 📜 догружает историю, 🧹 свои фильтры.")
    else:
        body = "Направлений пока нет."
    own = paged_rows(items, page, settings.PAGE_SIZE, lambda pg: NavCB(s="dirs", p=project.key, pg=pg))
    hidden = () if info.writable else ("dir_add",)
    await show(message, edit, "dirs", project, body=body, note=note, own=own, pg=page, hidden=hidden)


# ── 🔀 Направление ──────────────────────────────────────────────────────────


@view("dir")
async def direction_view(message: Message, edit: bool, nav: NavCB, state: FSMContext, note: str = "",
                         **_) -> None:
    project = status.find(nav.p)
    if project is None:
        await message.answer(texts.NO_PROJECT)
        return
    await show_direction(message, edit, project, nav.i, nav.pg, note)


async def show_direction(message: Message, edit: bool, project: Project, index: int, page: int,
                         note: str = "") -> None:
    info = status.project_info(project)
    d = direction(project, index)
    if d is None:
        await show_directions(message, edit, project, page, texts.config_error("stale"))
        return
    mode, edit_on, delete_on = effective(d, info.data)
    delay = d.get("send_delay")
    own = d.get("filters")
    body = "\n".join([
        f"<b>№ {index + 1}</b>",
        f"📨 Из: {texts.refs(d.get('from') or [])}",
        f"🎯 В: {texts.refs(d.get('to') or [])}",
        "🧹 Фильтры: " + (", ".join(esc(configstore.filter_name(f)) for f in own) if own else "общие"),
        "<i>Правки, удаления и режим без своей настройки берутся из 🔧 Параметры.</i>",
    ])
    titles = {
        "dir_edits": f"{title('dir_edits')}: {texts.on_off(edit_on)}",
        "dir_dels": f"{title('dir_dels')}: {texts.on_off(delete_on)}",
        "dir_mode": f"{title('dir_mode')}: {MODES.get(mode, mode)}",
        "dir_delay": f"{title('dir_delay')}: " + ("по умолч." if delay is None else f"{delay} с"),
        "dir_hist": f"{title('dir_hist')}: {texts.history_text(d.get('past_mode'))}",
        "dir_rdelay": f"{title('dir_rdelay')}: {replay_delay_text(d)}",
        "dir_link": f"{title('dir_link')}: " + ("своя" if d.get("fallback_link_url") else "общая"),
    }
    hidden = () if info.writable else tuple(a for a in titles) + ("dir_src", "dir_dst", "dir_del")
    if not d.get("past_mode") and "dir_rdelay" not in hidden:
        hidden += ("dir_rdelay",)
    await show(message, edit, "dir", project, body=body, note=note, titles=titles, hidden=hidden,
               i=index, pg=page, h=configstore.fingerprint(d))


async def _write(callback: CallbackQuery, project: Project, cb: ActCB, mutate, store: ConfigStore,
                 sysd: Systemd, after_list: bool = False) -> None:
    await callback.answer()

    async def after(message: Message, done: str) -> None:
        if after_list:
            await show_directions(message, True, project, cb.pg, done)
        else:
            await show_direction(message, True, project, cb.i, cb.pg, done)

    await save(message_of(callback), True, project, lambda p: store.update(p, mutate), after,
               NavCB(s="dirs", p=project.key, pg=cb.pg), sysd)


@on_action(router, "dir_edits", "dir_dels", "dir_mode")
async def on_toggle(callback: CallbackQuery, callback_data: ActCB, store: ConfigStore, sysd: Systemd) -> None:
    cb = callback_data
    project = await project_of(callback, cb.p)
    if project is None:
        return
    if direction(project, cb.i, cb.h) is None:
        await stale_tap(callback, texts.config_error("stale"))
        return

    def mutate(cfg: Any) -> None:
        if cb.a == "dir_mode":
            configstore.toggle_direction_mode(cfg, cb.i, cb.h)
        else:
            flag = "disable_edit" if cb.a == "dir_edits" else "disable_delete"
            configstore.toggle_direction_flag(cfg, cb.i, cb.h, flag)

    await _write(callback, project, cb, mutate, store, sysd)


@on_action(router, "dir_del")
async def on_delete(callback: CallbackQuery, callback_data: ActCB, state: FSMContext) -> None:
    cb = callback_data
    project = await project_of(callback, cb.p)
    if project is None:
        return
    d = direction(project, cb.i, cb.h)
    if d is None:
        await stale_tap(callback, texts.config_error("stale"))
        return
    await ask_confirm(
        callback, state,
        f"{head('🗑 Удалить направление')} № {cb.i + 1}?\n\n📨 Из: {texts.refs(d.get('from') or [])}\n"
        f"🎯 В: {texts.refs(d.get('to') or [])}\n\nУже переданные сообщения останутся у получателей, "
        "но их правки и удаления больше не будут повторяться. Перед записью создаётся копия .bak.",
        "dir_del", NavCB(s="dir", p=project.key, i=cb.i, pg=cb.pg), yes=YES_DELETE,
        p=project.key, i=cb.i, h=cb.h, pg=cb.pg,
    )


@confirmed("dir_del")
async def do_delete(callback: CallbackQuery, action: dict, state: FSMContext, store: ConfigStore,
                    sysd: Systemd, **_) -> None:
    project = await project_of(callback, action["p"])
    if project is None:
        return
    cb = ActCB(a="dir_del", p=project.key, i=action["i"], pg=action["pg"], h=action["h"])
    await _write(callback, project, cb, lambda cfg: configstore.delete_direction(cfg, cb.i, cb.h),
                 store, sysd, after_list=True)


# ── typed values: 📨 Источники, 🎯 Получатели, ⏱ Задержка ──────────────────

PROMPTS = {
    "dir_src": "пришлите ID источников через запятую или с новой строки (можно с темой "
               "<code>#5</code>). Список заменится целиком.",
    "dir_dst": "пришлите ID получателей через запятую или с новой строки (можно с темой "
               "<code>#5</code>). Список заменится целиком.",
    "dir_delay": "пришлите число секунд между отправками (0–60, например <code>0.5</code>) или "
                 "<code>-</code>, чтобы вернуть значение по умолчанию.",
    "dir_rdelay": "пришлите число секунд между отправками при догрузке истории этого направления "
                  "(0–60, например <code>1.5</code>; больше — реже FloodWait) или <code>-</code>, "
                  f"чтобы вернуть {DEFAULT_REPLAY_DELAY} с.",
    "dir_link": "пришлите ссылку (<code>https://t.me/yourchannel</code>) — ею заменяются ссылки, "
                "которые зеркало не может переписать, — или <code>-</code>, чтобы брать общую из "
                "🔧 Параметры.",
}


@on_action(router, "dir_src", "dir_dst", "dir_delay", "dir_rdelay", "dir_link")
async def on_value(callback: CallbackQuery, callback_data: ActCB, state: FSMContext) -> None:
    cb = callback_data
    project = await project_of(callback, cb.p)
    if project is None:
        return
    d = direction(project, cb.i, cb.h)
    if d is None:
        await stale_tap(callback, texts.config_error("stale"))
        return
    if cb.a == "dir_delay":
        current = "по умолчанию" if d.get("send_delay") is None else f"{esc(d['send_delay'])} с"
    elif cb.a == "dir_rdelay":
        if not d.get("past_mode"):
            await stale_tap(callback, texts.config_error("no_history"))
            return
        current = replay_delay_text(d)
    elif cb.a == "dir_link":
        current = f"<code>{esc(d['fallback_link_url'])}</code>" if d.get("fallback_link_url") else "общая"
    else:
        current = texts.refs(d.get("from" if cb.a == "dir_src" else "to") or [])
    await start_form(
        callback, state, Input.value,
        f"{head(title(cb.a))} — направление № {cb.i + 1}, сейчас: {current}.\n\n{PROMPTS[cb.a]}",
        NavCB(s="dir", p=project.key, i=cb.i, pg=cb.pg),
        data={"kind": cb.a, "p": project.key, "i": cb.i, "h": cb.h, "pg": cb.pg},
    )


async def _typed(message: Message, state: FSMContext, data: dict, mutate, store: ConfigStore,
                 sysd: Systemd) -> None:
    project = status.find(data["p"])
    await leave_form(message.chat.id, state)
    if project is None:
        await message.answer(texts.NO_PROJECT)
        return

    async def after(target: Message, done: str) -> None:
        await show_direction(target, True, project, data["i"], data["pg"], done)

    await save(message, False, project, lambda p: store.update(p, mutate), after,
               NavCB(s="dir", p=project.key, i=data["i"], pg=data["pg"]), sysd)


@input_kind("dir_src")
@input_kind("dir_dst")
async def set_refs(message: Message, state: FSMContext, raw: str, data: dict, store: ConfigStore,
                   sysd: Systemd, **_) -> None:
    try:
        refs = configstore.parse_chat_refs(raw)
    except ConfigError as e:
        await message.answer(f"{texts.config_error(e.code, e.detail)}\nПришлите ещё раз:")
        return
    side = "from" if data["kind"] == "dir_src" else "to"
    await _typed(message, state, data,
                 lambda cfg: configstore.set_direction_refs(cfg, data["i"], data["h"], side, refs), store, sysd)


@input_kind("dir_delay")
async def set_delay(message: Message, state: FSMContext, raw: str, data: dict, store: ConfigStore,
                    sysd: Systemd, **_) -> None:
    try:
        delay = None if raw == configstore.CLEAR else configstore.parse_delay(raw)
    except ConfigError as e:
        await message.answer(f"{texts.config_error(e.code, e.detail)}\nПришлите ещё раз:")
        return
    await _typed(message, state, data,
                 lambda cfg: configstore.set_direction_value(cfg, data["i"], data["h"], "send_delay", delay),
                 store, sysd)


@input_kind("dir_rdelay")
async def set_replay_delay(message: Message, state: FSMContext, raw: str, data: dict, store: ConfigStore,
                           sysd: Systemd, **_) -> None:
    try:
        delay = None if raw == configstore.CLEAR else configstore.parse_delay(raw)
    except ConfigError as e:
        await message.answer(f"{texts.config_error(e.code, e.detail)}\nПришлите ещё раз:")
        return
    await _typed(message, state, data,
                 lambda cfg: configstore.set_direction_replay_delay(cfg, data["i"], data["h"], delay),
                 store, sysd)


@input_kind("dir_link")
async def set_link(message: Message, state: FSMContext, raw: str, data: dict, store: ConfigStore,
                   sysd: Systemd, **_) -> None:
    try:
        url = None if raw == configstore.CLEAR else configstore.parse_url(raw)
    except ConfigError as e:
        await message.answer(f"{texts.config_error(e.code, e.detail)}\nПришлите ещё раз:")
        return
    await _typed(message, state, data,
                 lambda cfg: configstore.set_direction_value(cfg, data["i"], data["h"], "fallback_link_url", url),
                 store, sysd)


# ── 📜 История ──────────────────────────────────────────────────────────────

HISTORY = [("⏭ Не копировать", "none"), ("📚 Всю", "full"), ("🔢 Последние N…", "last"), ("📅 С даты…", "since")]


@on_action(router, "dir_hist")
async def on_history(callback: CallbackQuery, callback_data: ActCB, state: FSMContext) -> None:
    cb = callback_data
    project = await project_of(callback, cb.p)
    if project is None:
        return
    d = direction(project, cb.i, cb.h)
    if d is None:
        await stale_tap(callback, texts.config_error("stale"))
        return
    await start_form(
        callback, state, Input.value,
        f"{head(title('dir_hist'))} — направление № {cb.i + 1}, сейчас: {texts.history_text(d.get('past_mode'))}.\n\n"
        f"Какую историю источника копировать при {head('⏪ Догрузка')}?",
        NavCB(s="dir", p=project.key, i=cb.i, pg=cb.pg), markup=choice_kb("hist", HISTORY, widths=(2,)),
        data={"kind": "hist", "p": project.key, "i": cb.i, "h": cb.h, "pg": cb.pg}, choice=True,
    )


@router.callback_query(Input.value, ChoiceCB.filter(F.scope == "hist"))
async def on_history_pick(callback: CallbackQuery, callback_data: ChoiceCB, state: FSMContext,
                          store: ConfigStore, sysd: Systemd) -> None:
    data = await state.get_data()
    if data.get("kind") != "hist":
        await stale_tap(callback)
        return
    await callback.answer()
    if callback_data.value in ("last", "since"):
        kind = "dir_last" if callback_data.value == "last" else "dir_since"
        ask_text = ("пришлите количество последних сообщений (1–1000000):" if kind == "dir_last" else
                    "пришлите дату, с которой копировать: <code>2024-01-31</code> или "
                    "<code>2024-01-31T12:00:00</code>:")
        with suppress(Exception):
            await message_of(callback).edit_reply_markup(reply_markup=None)
        await ask(message_of(callback), state, Input.value, f"{head(title('dir_hist'))} — {ask_text}", kind=kind)
        return
    value = None if callback_data.value == "none" else {"full_history": True}
    project = status.find(data["p"])
    await leave_form(callback.from_user.id, state)
    if project is None:
        await stale_tap(callback, texts.NO_PROJECT)
        return

    async def after(target: Message, done: str) -> None:
        await show_direction(target, True, project, data["i"], data["pg"], done)

    await save(message_of(callback), True, project,
               lambda p: store.update(p, lambda cfg: configstore.set_direction_value(
                   cfg, data["i"], data["h"], "past_mode", value)),
               after, NavCB(s="dir", p=project.key, i=data["i"], pg=data["pg"]), sysd)


@input_kind("hist")
async def history_typed(message: Message, state: FSMContext, raw: str, data: dict, **_) -> None:
    await message.answer("Выберите вариант кнопкой выше — или /cancel, чтобы выйти.")


@input_kind("dir_last")
@input_kind("dir_since")
async def set_history(message: Message, state: FSMContext, raw: str, data: dict, store: ConfigStore,
                      sysd: Systemd, **_) -> None:
    try:
        pm = ({"last_n": configstore.parse_last_n(raw)} if data["kind"] == "dir_last"
              else {"since_date": configstore.parse_since(raw)})
    except ConfigError as e:
        await message.answer(f"{texts.config_error(e.code, e.detail)}\nПришлите ещё раз:")
        return
    await _typed(message, state, data,
                 lambda cfg: configstore.set_direction_value(cfg, data["i"], data["h"], "past_mode", pm),
                 store, sysd)


# ── ➕ Добавить: source → targets → mode → history ──────────────────────────

ADD = title("dir_add")
SOURCE_ASK = (f"{head(ADD)} — шаг 1 из 4. Пришлите ID <b>источника</b>: <code>-1001234567890</code> "
              "или с темой: <code>-1001234567890#5</code>.")


@on_action(router, "dir_add")
async def on_add(callback: CallbackQuery, callback_data: ActCB, state: FSMContext) -> None:
    project = await project_of(callback, callback_data.p)
    if project is None:
        return
    if not status.project_info(project).writable:
        await stale_tap(callback, texts.config_error("read_only"))
        return
    await start_form(callback, state, AddDirection.source, SOURCE_ASK, NavCB(s="dirs", p=project.key),
                     data={"p": project.key})


@router.message(AddDirection.source)
async def on_add_source(message: Message, state: FSMContext) -> None:
    try:
        source = configstore.normalize_chat_ref(message.text or "")
    except ConfigError as e:
        await message.answer(f"{texts.config_error(e.code, e.detail)}\nПришлите ещё раз:")
        return
    await ask(message, state, AddDirection.targets,
              f"{head(ADD)} — шаг 2 из 4. Источник: {texts.refs([source])}.\n\nПришлите ID "
              "<b>получателей</b> через запятую или с новой строки (можно с темой <code>#5</code>).",
              source=source)


@router.message(AddDirection.targets)
async def on_add_targets(message: Message, state: FSMContext) -> None:
    try:
        targets = configstore.parse_chat_refs(message.text or "")
    except ConfigError as e:
        await message.answer(f"{texts.config_error(e.code, e.detail)}\nПришлите ещё раз:")
        return
    source = (await state.get_data())["source"]
    await ask(message, state, AddDirection.choice,
              f"{head(ADD)} — шаг 3 из 4. {texts.refs([source])} → {texts.refs(targets)}\n\n"
              "Режим:\n• <b>копия</b> — от имени получателя, работают все фильтры\n"
              "• <b>пересылка</b> — с подписью «Переслано из»; фильтры, меняющие содержимое, с ней "
              "недопустимы",
              choice_kb("add_mode", [("📋 Копия", "copy"), ("↪️ Пересылка", "forward")], widths=(2,)),
              targets=targets)


@router.callback_query(AddDirection.choice, ChoiceCB.filter(F.scope == "add_mode"))
async def on_add_mode(callback: CallbackQuery, callback_data: ChoiceCB, state: FSMContext) -> None:
    if callback_data.value not in MODES:
        await stale_tap(callback)
        return
    await callback.answer()
    data = await state.update_data(mode=callback_data.value)
    await message_of(callback).edit_text(
        f"{head(ADD)} — шаг 4 из 4. {texts.refs([data['source']])} → {texts.refs(data['targets'])} · "
        f"{MODES[data['mode']]}\n\nКопировать историю источника при {head('⏪ Догрузка')}?",
        reply_markup=choice_kb("add_hist", [("⏭ Без истории", "no"), ("📚 Всю историю", "full")], widths=(2,)),
    )


@router.callback_query(AddDirection.choice, ChoiceCB.filter(F.scope == "add_hist"))
async def on_add_history(callback: CallbackQuery, callback_data: ChoiceCB, state: FSMContext,
                         store: ConfigStore, sysd: Systemd) -> None:
    data = await state.get_data()
    if "mode" not in data:
        await stale_tap(callback)
        return
    project = status.find(data["p"])
    await leave_form(callback.from_user.id, state)
    if project is None:
        await stale_tap(callback, texts.NO_PROJECT)
        return
    await callback.answer()
    full = callback_data.value == "full"

    async def after(target: Message, done: str) -> None:
        await show_directions(target, True, project, -1, done)  # the last page: the new one

    await save(
        message_of(callback), True, project,
        lambda p: store.update(p, lambda cfg: configstore.add_direction(
            cfg, [data["source"]], data["targets"], data["mode"], full)),
        after, NavCB(s="dirs", p=project.key), sysd,
    )


@router.message(AddDirection.choice)
async def on_add_choice_typed(message: Message) -> None:
    await message.answer("Выберите вариант кнопкой выше — или /cancel, чтобы выйти.")
