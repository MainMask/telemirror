"""🔀 Направления: the list (🔎 Найти in it), one direction's card, its
channels (📨 Откуда / 🎯 Куда: a list to add to and remove from), ➕ Добавить.
A channel is typed as its id or given by a post forwarded from it. What is
the same for every direction — edits, deletes, mode, history, the link — is
set once for the project (⚙️ Настройки проекта, ⏪ История); a
direction's own value of those is hand-written and only shown here."""

import logging
from typing import Any, Optional

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import configedit, configparse, filtercatalog, settings, status, texts
from bot.callbacks import ActCB, ChoiceCB, NavCB
from bot.configparse import ConfigError
from bot.configstore import ConfigStore
from bot.keyboards.common import button, cancel_kb, choice_kb, markup, paged_rows, pages, pick_kb
from bot.registry import BACK, ROW_REMOVE, SCREENS, TITLES, YES_DELETE, title
from bot.routers._common import (
    ask,
    ask_confirm,
    confirmed,
    end_form,
    input_kind,
    message_of,
    on_action,
    project_of,
    remember_chat,
    retry,
    stale_tap,
    start_form,
)
from bot.screens import open_screen, show, view
from bot.states import AddDirection, Input, leave_form
from bot.texts import esc, head
from bot.writes import save, saved_note
from telemirror import stats
from telemirror.projects import Project

logger = logging.getLogger(__name__)
router = Router(name="directions")

REPLAY = SCREENS["rpl"].title
FIND_MAX = 20  # 🔎 Найти: matches shown
SILENT_DAYS = 7  # 🔇: as the weekly report's «Ничего не пришло за неделю»


def effective(d: Any, data: Any) -> tuple:
    """(mode, edits repeated, deletes repeated): the direction's own, else the project's."""
    mode = str(d.get("mode", data.get("mode", "copy")))
    edit_on = not bool(d.get("disable_edit", data.get("disable_edit", False)))
    delete_on = not bool(d.get("disable_delete", data.get("disable_delete", False)))
    return mode, edit_on, delete_on


def own_settings(d: Any) -> list:
    """A direction's hand-written values of the project-wide settings, in words."""
    out = []
    if "mode" in d:
        out.append(f"режим «{texts.mode_text(d['mode'])}»")
    if "disable_edit" in d:
        out.append(f"правки {texts.on_off(not d['disable_edit'])}")
    if "disable_delete" in d:
        out.append(f"удаления {texts.on_off(not d['disable_delete'])}")
    if d.get("fallback_link_url"):
        out.append(f"ссылка вместо чужих <code>{esc(d['fallback_link_url'])}</code>")
    pm = d.get("past_mode")
    if isinstance(pm, dict) and pm.get("send_delay") is not None:
        out.append(f"пауза при копировании истории {esc(pm['send_delay'])} с")
    return out


def direction(project: Project, index: int, fp: str = "") -> Optional[Any]:
    """The direction at ``index`` — None if gone, or changed when ``fp`` is given."""
    dirs = status.project_info(project).directions
    if not 0 <= index < len(dirs) or (fp and configedit.fingerprint(dirs[index]) != fp):
        return None
    return dirs[index]


def _list(project: Project, page: int = 0) -> NavCB:
    return NavCB(s="dirs", p=project.key, pg=page)


def _card(project: Project, index: int, page: int) -> NavCB:
    return NavCB(s="dir", p=project.key, i=index, pg=page)


# how to give a channel, in every prompt that asks for one
CHAT_HOW = (f"нажмите {head(TITLES['pick'])}, перешлите сюда любой пост из канала или пришлите его ID: "
            "<code>-1001234567890</code> (тема группы — <code>-1001234567890#5</code>).")


def _chats(d: Any) -> list:
    return [*(d.get("from") or []), *(d.get("to") or [])]


def _later(d: Any, names: dict) -> str:
    """The note under a direction whose channels aren't all known by name."""
    return "\n" + texts.NAMES_LATER if texts.any_unnamed(_chats(d), names) else ""


def _quiet(d: Any, counts: dict) -> Optional[int]:
    """stats.quiet_days of the direction's channels (sources × targets)."""
    ids = [[texts._split(r)[0] for r in d.get(k) or []] for k in ("from", "to")]
    return stats.quiet_days(counts, [(s, t) for s in ids[0] for t in ids[1] if s is not None and t is not None])


def _silent(days: Optional[int]) -> bool:
    return days is not None and days >= SILENT_DAYS


def _last_post(days: Optional[int]) -> str:
    if days is None:
        return "пока нет данных"
    if days > stats.KEEP_DAYS:
        return f"больше {stats.KEEP_DAYS} дн. назад"
    return {0: "сегодня", 1: "вчера"}.get(days, f"{days} дн. назад")


def _row(n: int, d: Any, names: dict, counts: dict) -> str:
    """A direction's button: «3. Источник → Канал» and its marks."""
    marks = (" 🧹" if d.get("filters") else "") + (" ✳️" if own_settings(d) else "") + \
        (" 🔇" if _silent(_quiet(d, counts)) else "")
    return (f"{n + 1}. {texts.short_refs(list(d.get('from') or []), names)} → "
            f"{texts.short_refs(list(d.get('to') or []), names)}{marks}")


# ── 🔀 Направления ──────────────────────────────────────────────────────────


@view("dirs")
async def directions_view(message: Message, edit: bool, nav: NavCB, *, project: Project, note: str = "",
                          **_) -> None:
    info = status.project_info(project)
    dirs, names = info.directions, info.names
    count = pages(len(dirs), settings.PAGE_SIZE)
    page = nav.pg % count
    counts = stats.load(project.key)
    items = [button(_row(n, d, names, counts), _card(project, n, page)) for n, d in enumerate(dirs)]
    if not info.readable:
        body = texts.unreadable(info)
    elif dirs:
        body = f"Всего: <b>{len(dirs)}</b> · стр. {page + 1}/{count}. Каждая строка — откуда → куда."
        if silent := sum(_silent(_quiet(d, counts)) for d in dirs):
            body += f"\n🔇 Молчат {SILENT_DAYS} дней и больше: <b>{silent}</b>."
        if any(d.get("filters") or own_settings(d) for d in dirs):
            body += "\nЗначки: 🧹 свои фильтры, ✳️ свои настройки в файле."
        if any(texts.any_unnamed(_chats(d), names) for d in dirs):
            body += "\n" + texts.NAMES_LATER
    else:
        body = ("Направлений пока нет. Направление — это откуда (канал-источник) и куда "
                "(ваши каналы) копировать посты.")
    own = paged_rows(items, page, settings.PAGE_SIZE, lambda pg: _list(project, pg))
    hidden: tuple = () if info.writable else ("dir_add",)
    if not dirs:
        hidden += ("dir_find",)
    await show(message, edit, "dirs", project, body=body, note=note, own=own, pg=page, hidden=hidden)


@on_action(router, "dir_find")
async def on_find(callback: CallbackQuery, callback_data: ActCB, project: Project, state: FSMContext) -> None:
    await start_form(
        callback, state, Input.value,
        f"{head(title('dir_find'))} — пришлите часть названия канала или его ID, перешлите пост из канала "
        f"или нажмите {head(TITLES['pick'])}. Ищется и среди источников, и среди ваших каналов.",
        _list(project, callback_data.pg), markup=pick_kb(), data={"kind": "dir_find", "p": project.key},
    )


@input_kind("dir_find")
async def find(message: Message, state: FSMContext, raw: str, data: dict, project: Project, **_) -> None:
    await leave_form(message.chat.id, state)
    info = status.project_info(project)
    names, query, counts = info.names, raw.casefold(), stats.load(project.key)

    def hit(ref: Any) -> bool:
        chat_id = texts._split(ref)[0]
        return query in str(ref) or query in names.get(chat_id, "").casefold()

    found = [(n, d) for n, d in enumerate(info.directions) if any(hit(r) for r in _chats(d))]
    rows = [[button(_row(n, d, names, counts), _card(project, n, n // settings.PAGE_SIZE))] for n, d in found[:FIND_MAX]]
    rows.append([button(title("dir_find"), ActCB(a="dir_find", p=project.key)),
                 button(BACK, _list(project))])
    if not found:
        text = f"{head(title('dir_find'))}: «{esc(raw)}» — ничего не найдено."
    else:
        more = f" Показаны первые {FIND_MAX} — уточните запрос." if len(found) > FIND_MAX else ""
        text = f"{head(title('dir_find'))}: «{esc(raw)}» — найдено: <b>{len(found)}</b>.{more}"
    await message.answer(text, reply_markup=markup(rows))


# ── 🔀 Направление ──────────────────────────────────────────────────────────


@view("dir")
async def direction_view(message: Message, edit: bool, nav: NavCB, *, project: Project, note: str = "",
                         **_) -> None:
    info = status.project_info(project)
    d = direction(project, nav.i)
    if d is None:
        await directions_view(message, edit, _list(project, nav.pg), project=project,
                              note=texts.config_error("stale"))
        return
    names = info.names
    filters = d.get("filters")
    delay = d.get("send_delay")
    lines = [
        f"<b>№ {nav.i + 1}</b>",
        f"📨 Откуда: {texts.refs(d.get('from') or [], names)}",
        f"🎯 Куда: {texts.refs(d.get('to') or [], names)}",
        "🧹 Фильтры: " + (", ".join(esc(filtercatalog.display_name(configedit.filter_name(f))) for f in filters)
                         if filters else "общие для проекта"),
        f"📜 Старые посты: {texts.history_text(d.get('past_mode'))}",
    ]
    days = _quiet(d, stats.load(project.key))
    lines.append(f"🕰 Последний пост: {_last_post(days)}" + (" 🔇" if _silent(days) else ""))
    more = (f"Правки, удаления и режим — общие для всех направлений: {SCREENS['mng'].title}; "
            f"старые посты — {REPLAY}. Последний пост — по подсчётам зеркала: пока оно остановлено, "
            f"источник тоже выглядит молчащим.{_later(d, names)}")
    if own := own_settings(d):
        lines.append(f"✳️ У этого направления в файле настроек свои: {', '.join(own)}.")
    titles = {"dir_delay": f"{title('dir_delay')}: " + ("по умолчанию" if delay is None else f"{delay} с")}
    hidden = () if info.writable else ("dir_src", "dir_dst", "dir_delay", "dir_del")
    await show(message, edit, "dir", project, body="\n".join(lines), more=more, note=note,
               titles=titles, hidden=hidden, i=nav.i, pg=nav.pg, h=configedit.fingerprint(d))


async def _tapped(callback: CallbackQuery, project: Project, cb: ActCB) -> Optional[Any]:
    """The tapped direction; None after saying the list changed under the button."""
    d = direction(project, cb.i, cb.h)
    if d is None:
        await stale_tap(callback, texts.config_error("stale"))
    return d


@on_action(router, "dir_del")
async def on_delete(callback: CallbackQuery, callback_data: ActCB, project: Project, state: FSMContext) -> None:
    cb = callback_data
    if (d := await _tapped(callback, project, cb)) is None:
        return
    names = status.project_info(project).names
    await ask_confirm(
        callback, state,
        f"{head(title('dir_del'))} направление № {cb.i + 1}?\n\n📨 Откуда: {texts.refs(d.get('from') or [], names)}\n"
        f"🎯 Куда: {texts.refs(d.get('to') or [], names)}\n\nУже скопированные посты останутся в ваших каналах, "
        f"но их правки и удаления больше не будут повторяться. Прошлую версию настроек можно вернуть: "
        f"{title('cfg_undo')}.",
        "dir_del", _card(project, cb.i, cb.pg), yes=YES_DELETE, p=project.key, i=cb.i, h=cb.h, pg=cb.pg,
    )


@confirmed("dir_del")
async def do_delete(callback: CallbackQuery, action: dict, project: Project, store: ConfigStore, deps: dict,
                    **_) -> None:
    await callback.answer()
    await save(message_of(callback), True, project,
               lambda p: store.update(p, lambda cfg: configedit.delete_direction(cfg, action["i"], action["h"])),
               _list(project, action["pg"]), deps)


# ── ⏱ Пауза между постами ───────────────────────────────────────────────────

DELAY_ASK = ("Пришлите, сколько секунд ждать между отправками (0–60, например <code>0.5</code>), или "
             "<code>-</code>, чтобы вернуть значение по умолчанию. Обычно менять не нужно: пауза помогает, "
             "если Telegram ограничивает частые отправки.")


@on_action(router, "dir_delay")
async def on_delay(callback: CallbackQuery, callback_data: ActCB, project: Project, state: FSMContext) -> None:
    cb = callback_data
    if (d := await _tapped(callback, project, cb)) is None:
        return
    current = "по умолчанию" if d.get("send_delay") is None else f"{esc(d['send_delay'])} с"
    await start_form(
        callback, state, Input.value,
        f"{head(title('dir_delay'))} — направление № {cb.i + 1}, сейчас: {current}.\n\n{DELAY_ASK}",
        _card(project, cb.i, cb.pg),
        data={"kind": "dir_delay", "p": project.key, "i": cb.i, "h": cb.h, "pg": cb.pg},
    )


@input_kind("dir_delay")
async def set_delay(message: Message, state: FSMContext, raw: str, data: dict, project: Project,
                    store: ConfigStore, deps: dict, **_) -> None:
    delay = None if raw == configparse.CLEAR else configparse.parse_delay(raw)
    await leave_form(message.chat.id, state)
    await save(message, False, project,
               lambda p: store.update(p, lambda cfg: configedit.set_direction_value(
                   cfg, data["i"], data["h"], "send_delay", delay)),
               _card(project, data["i"], data["pg"]), deps)


# ── 📨 Откуда / 🎯 Куда: the direction's channels, one by one ───────────────

SIDES = {"dir_src": "from", "dir_dst": "to"}
REFS_ADD = {"dir_src": "Добавить источник", "dir_dst": "Добавить канал, куда копировать"}


def _refs_form(project: Project, kind: str, index: int) -> tuple:
    """(text, keyboard) of a direction's channel list: 🗑 one, ✅ Готово (every
    change is saved at once — there's nothing to cancel)."""
    info = status.project_info(project)
    d, names = info.directions[index], info.names
    current = list(d.get(SIDES[kind]) or [])
    lines = [f"{head(title(kind))} — направление № {index + 1}:"]
    lines += [f"{n + 1}. {texts.chat(r, names)}" for n, r in enumerate(current)] or [texts.UNKNOWN]
    lines.append(f"\n<b>{REFS_ADD[kind]}</b>: {CHAT_HOW}")
    lines.append(f"Убрать — кнопка {ROW_REMOVE} с его названием. Всё сохраняется сразу; закончили — "
                 f"{TITLES['done']}.")
    if texts.any_unnamed(current, names):
        lines.append(texts.NAMES_LATER)
    options = [(f"{ROW_REMOVE} {texts.chat_plain(r, names, 40)}", f"x{configparse.ref_str(r)}") for r in current]
    options.append((TITLES["done"], "done"))
    return "\n".join(lines), pick_kb(choice_kb("refs", options))


@on_action(router, "dir_src", "dir_dst")
async def on_refs(callback: CallbackQuery, callback_data: ActCB, project: Project, state: FSMContext) -> None:
    cb = callback_data
    if await _tapped(callback, project, cb) is None:
        return
    text, kb = _refs_form(project, cb.a, cb.i)
    await callback.answer()
    await leave_form(callback.from_user.id, state)
    await state.set_state(Input.value)
    await state.update_data(origin=_card(project, cb.i, cb.pg).pack(), kind=cb.a, p=project.key, i=cb.i,
                            h=cb.h, pg=cb.pg)
    await message_of(callback).answer(text, reply_markup=kb)


async def _save_refs(message: Message, edit: bool, state: FSMContext, data: dict, project: Project,
                     refs: list, store: ConfigStore, deps: dict, done: str) -> None:
    """The direction's list replaced by ``refs``; the list shown again, still
    open, ``done`` on top (how to apply it is said once, at ✅ Готово)."""

    async def reopen(target: Message, _note: str) -> None:
        d = direction(project, data["i"])
        if d is None:
            await end_form(target, state, texts.config_error("stale"), edit=True)
            return
        await state.update_data(h=configedit.fingerprint(d), changed=True)
        text, kb = _refs_form(project, data["kind"], data["i"])
        await target.edit_text(f"{done}\n\n{text}", reply_markup=kb)

    side = SIDES[data["kind"]]
    ok = await save(
        message, edit, project,
        lambda p: store.update(p, lambda cfg: configedit.set_direction_refs(cfg, data["i"], data["h"], side, refs)),
        reopen, deps, back=_card(project, data["i"], data["pg"]),
    )
    if not ok:
        await leave_form(message.chat.id, state)


def _current(d: Any, kind: str) -> list:
    return [configparse.ref_str(r) for r in d.get(SIDES[kind]) or []]


@input_kind("dir_src")
@input_kind("dir_dst")
async def add_refs(message: Message, state: FSMContext, raw: str, data: dict, project: Project,
                   store: ConfigStore, deps: dict, **_) -> None:
    new = configparse.parse_chat_refs(raw)
    d = direction(project, data["i"], data["h"])
    if d is None:
        await end_form(message, state, texts.config_error("stale"))
        return
    current = _current(d, data["kind"])
    added = [r for r in new if r not in current]
    if not added:
        await message.answer(f"Этот канал уже в списке. {texts.SEND_AGAIN}")
        return
    await _save_refs(message, False, state, data, project, current + added, store, deps,
                     f"✅ Добавлено: {texts.refs(added, status.project_info(project).names)}.")


@router.callback_query(Input.value, ChoiceCB.filter(F.scope == "refs"))
async def on_refs_pick(callback: CallbackQuery, callback_data: ChoiceCB, state: FSMContext,
                       store: ConfigStore, deps: dict) -> None:
    data = await state.get_data()
    if data.get("kind") not in SIDES:
        await stale_tap(callback)
        return
    if (project := await project_of(callback, data["p"])) is None:
        return
    if callback_data.value == "done":
        await callback.answer()
        await leave_form(callback.from_user.id, state)
        note = await saved_note(project, deps) if data.get("changed") else ""
        await open_screen(_card(project, data["i"], data["pg"]), message_of(callback), True, deps, note=note)
        return
    d = direction(project, data["i"], data["h"])
    current = _current(d, data["kind"]) if d is not None else []
    ref = callback_data.value[1:]
    if ref not in current:
        await stale_tap(callback, texts.config_error("stale"))
        return
    if len(current) == 1:
        await stale_tap(callback, texts.config_error("no_refs"))
        return
    await callback.answer()
    names = status.project_info(project).names
    await _save_refs(message_of(callback), True, state, data, project, [r for r in current if r != ref],
                     store, deps, f"✅ Убрано: {texts.chat(ref, names)}.")


# ── ➕ Добавить: source → targets → mode → history ──────────────────────────

ADD = TITLES["dir_new"]
SOURCE_ASK = f"{head(ADD)} — шаг 1 из 3. <b>Откуда</b> копировать? Чтобы указать канал-источник, {CHAT_HOW}"
ADD_HISTORY = [(TITLES["hist_none"], "hist_none"), (TITLES["hist_full"], "hist_full")]


def _names_of(key: str) -> dict:
    project = status.find(key)
    return status.project_info(project).names if project else {}


def _typed_or_forwarded(message: Message, key: str) -> str:
    project = status.find(key)
    return (remember_chat(project, message) if project else None) or (message.text or "")


@on_action(router, "dir_add")
async def on_add(callback: CallbackQuery, project: Project, state: FSMContext) -> None:
    if not status.project_info(project).writable:
        await stale_tap(callback, texts.config_error("read_only"))
        return
    await start_form(callback, state, AddDirection.source, SOURCE_ASK, _list(project), markup=pick_kb(),
                     data={"p": project.key})


@router.message(AddDirection.source)
async def on_add_source(message: Message, state: FSMContext) -> None:
    key = (await state.get_data())["p"]
    try:
        source = configparse.normalize_chat_ref(_typed_or_forwarded(message, key))
    except ConfigError as e:
        await retry(message, e)
        return
    await ask(message, state, AddDirection.targets,
              f"{head(ADD)} — шаг 2 из 3. Откуда: {texts.refs([source], _names_of(key))}.\n\n"
              f"<b>Куда</b> копировать? Чтобы указать ваш канал, {CHAT_HOW} Можно несколько: присылайте "
              "по одному или ID через запятую.", pick_kb(),
              source=source, targets=[])


@router.message(AddDirection.targets)
async def on_add_targets(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    try:
        new = configparse.parse_chat_refs(_typed_or_forwarded(message, data["p"]))
    except ConfigError as e:
        await retry(message, e)
        return
    targets = data.get("targets", []) + [t for t in new if t not in data.get("targets", [])]
    await ask(message, state, AddDirection.targets,
              f"{head(ADD)} — шаг 2 из 3. {texts.refs([data['source']], _names_of(data['p']))} → "
              f"{texts.refs(targets, _names_of(data['p']))}\n\nДобавьте ещё канал или нажмите "
              f"{head(TITLES['done'])}.",
              pick_kb(choice_kb("add_targets", [(TITLES["done"], "done")])), targets=targets)


@router.callback_query(AddDirection.targets, ChoiceCB.filter(F.scope == "add_targets"))
async def on_add_targets_done(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not data.get("targets"):
        await stale_tap(callback)
        return
    await callback.answer()
    await state.set_state(AddDirection.choice)
    project = status.find(data["p"])
    info = status.project_info(project) if project else None
    names = info.names if info else {}
    usual = ""
    if info and (kinds := {str(configedit.history_of(d)) for d in info.directions}) and len(kinds) == 1:
        usual = f" У остальных направлений сейчас: {texts.history_text(info.directions[0].get('past_mode'))}."
    await message_of(callback).edit_text(
        f"{head(ADD)} — шаг 3 из 3. {texts.refs([data['source']], names)} → {texts.refs(data['targets'], names)}\n\n"
        f"Скопировать и старые посты этого источника?{usual} Само копирование запускается кнопкой в "
        f"{head(REPLAY)}; там же выбирается, что копировать, для всех направлений сразу.",
        reply_markup=cancel_kb(str(AddDirection.choice.state), choice_kb("add_hist", ADD_HISTORY, widths=(2,))),
    )


@router.callback_query(AddDirection.choice, ChoiceCB.filter(F.scope == "add_hist"))
async def on_add_history(callback: CallbackQuery, callback_data: ChoiceCB, state: FSMContext,
                         store: ConfigStore, deps: dict) -> None:
    data = await state.get_data()
    if not data.get("targets"):
        await stale_tap(callback)
        return
    if (project := await project_of(callback, data["p"])) is None:
        return
    await leave_form(callback.from_user.id, state)
    await callback.answer()
    full = callback_data.value == "hist_full"
    check = (f"\n👉 Проверьте, что у аккаунта есть доступ к новым каналам: {title('ca_dry')} в "
             f"{SCREENS['ca'].title} (кнопка в {SCREENS['dirs'].title}).")
    await save(
        message_of(callback), True, project,
        lambda p: store.update(p, lambda cfg: configedit.add_direction(
            cfg, [data["source"]], data["targets"], str(cfg.get("mode", "copy")), full)),
        _list(project, -1), deps,  # the last page: the new one
        outcome=lambda done: done + check,
    )


@router.message(AddDirection.choice)
async def on_add_choice_typed(message: Message) -> None:
    await message.answer(texts.USE_BUTTONS)
