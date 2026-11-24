"""🧹 Фильтры: a project's filters (for directions without their own) and a
direction's own. Filters are added from ``filtercatalog.FILTER_ARGS``, deleted,
moved; a filter's card edits its args — list-like ones item by item, scalars
by a toggle or a typed value. Every write goes through ``ConfigStore.update``,
so a value telemirror.config refuses (a bad format, an empty keyword list) is refused
with its error and the file stays as it was."""

from collections.abc import Set as AbstractSet
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import configedit, configparse, filtercatalog, settings, status, texts
from bot.callbacks import ChoiceCB, FltCB, NavCB
from bot.configstore import ConfigStore
from bot.keyboards.common import button, choice_kb, paged_rows, pages, pick_kb
from bot.registry import (
    CHECKED,
    ROW_REMOVE,
    TITLES,
    UNCHECKED,
    YES_DELETE,
)
from bot.registry import title
from bot.routers._common import (
    ask,
    ask_confirm,
    confirmed,
    input_kind,
    message_of,
    project_of,
    stale_tap,
    start_form,
    with_project,
)
from bot.screens import show, view
from bot.states import Input, leave_form
from bot.texts import esc, head
from bot.writes import save
from telemirror.projects import Project

router = Router(name="filters")

NAMES_ASK = ("какие @имена убирать из текста?\n\nПришлите их, каждое с новой строки, так, как они написаны "
             "в постах — с <code>@</code>. Остальные упоминания останутся.")
ASK = {
    "set": "пришлите значения, каждое с новой строки.",
    "list": "пришлите значения, каждое с новой строки.",
    "ids": f"нажмите {head(TITLES['pick'])}, перешлите сюда пост из канала или пришлите ID каналов — через "
           "запятую или каждый с новой строки.",
    "map": "пришлите пары, каждую с новой строки, в виде <code>что =&gt; на что</code>, например "
           "<code>купить =&gt; приобрести</code>.",
    "text": "пришлите новое значение.\n\n<code>-</code> — вернуть значение по умолчанию.",
    "number": "пришлите число.\n\n<code>-</code> — вернуть значение по умолчанию.",
}
KEYWORD_HINT = ("\n\nСлова ищутся целиком, без учёта регистра; <code>@имена</code> и <code>#теги</code> пишите "
                "как есть.\n<i>Для опытных: шаблон поиска (регулярное выражение) — <code>r'шаблон'</code>.</i>")
PATTERN = "🔣"  # a keyword written as r'...' — a regex, not a word
PATTERN_NOTE = f"{PATTERN} — шаблон поиска (регулярное выражение, для опытных); остальное — обычные слова."


def _pattern(word: str) -> str:
    """r'...' → «🔣 ...» (the regex itself); a plain word as it is."""
    return f"{PATTERN} {word[2:-1]}" if word.startswith("r'") and word.endswith("'") else word


def _keyword(item: str) -> str:
    """A keywords value for people: a set's word, or a map's «word => replacement»."""
    word, sep, rest = item.partition(" => ")
    return _pattern(word) + (f" => {rest}" if sep else "")
FORMAT_HINT = ("\n\nВ подписи обязательно должно быть <code>{message_text}</code> — сюда встанет текст поста. "
               "Можно добавить <code>{channel_name}</code> (название источника), <code>{message_link}</code> "
               "(ссылка на пост), <code>{sender_title}</code> и <code>{sender_username}</code> (автор).")


def label(key: str) -> str:
    return filtercatalog.ARG_LABELS.get(key, key)


def _item_html(item: str, kind: str, int_keys: bool, names: dict, key: str = "") -> str:
    """A list value for the card: a channel by its name (ids, an id-keyed map),
    a keyword without its r'...' notation."""
    if key == "keywords":
        word, sep, rest = item.partition(" => ")
        shown = (f"{PATTERN} <code>{esc(word[2:-1])}</code>" if _pattern(word) != word else esc(word))
        return shown + (f" =&gt; {esc(rest)}" if sep else "")
    if kind == "ids":
        return texts.chat(item, names)
    if int_keys and " => " in item:
        chat_id, value = item.split(" => ", 1)
        return f"{texts.chat(chat_id, names)} =&gt; <code>{esc(value)}</code>"
    return f"<code>{esc(item)}</code>"


def _item_plain(item: str, kind: str, int_keys: bool, names: dict, key: str = "") -> str:
    """The same for a button (no HTML)."""
    if key == "keywords":
        return texts.cut(_keyword(item), 40)
    if kind == "ids":
        return texts.chat_plain(item, names, 40)
    if int_keys and " => " in item:
        chat_id, value = item.split(" => ", 1)
        return texts.cut(f"{texts.chat_plain(chat_id, names)} => {value}", 40)
    return texts.cut(item, 40)


def _arg_text(a: Any, names: dict) -> str:
    """An arg's value in the list's line: channels by their names."""
    if a.kind == "ids":
        return ", ".join(texts.chat_plain(v, names) for v in a.value or [])
    if isinstance(a.value, bool):
        return texts.on_off(a.value)
    if a.key == "keywords" and a.value:
        value = a.value
        items = [f"{k} => {v}" for k, v in value.items()] if isinstance(value, dict) else sorted(map(str, value))
        return _short([_keyword(v) for v in items])
    return _short(a.value)


def name_of(entry: Any) -> str:
    return filtercatalog.display_name(configedit.filter_name(entry))


def _short(value: Any, limit: int = 60) -> str:
    if isinstance(value, AbstractSet):  # incl. ruamel's CommentedSet (a !!set)
        value = sorted(str(v) for v in value)
    if isinstance(value, dict):
        value = [f"{k} => {v}" for k, v in value.items()]
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(v) for v in value)
    return texts.cut(str(value), limit)


def _ask_text(entry: Any, key: str, kind: str) -> str:
    text = ASK[kind]
    if key == "keywords" and kind != "map":
        text += KEYWORD_HINT
    if key == "format":
        text += FORMAT_HINT
    if configedit.int_keys(entry, key):
        text = "пришлите пары, каждую с новой строки: <code>-1001234567890 =&gt; Имя канала</code>."
    return text


def _back(project: Project, d: int) -> NavCB:
    """The list the filter is in: the project's (d < 0) or the direction's —
    with the page of 🔀 Направления the direction is on, for ⬅️ further back."""
    return NavCB(s="flt", p=project.key) if d < 0 else NavCB(s="dflt", p=project.key, i=d, pg=d // settings.PAGE_SIZE)


def _card(project: Project, d: int, f: int) -> NavCB:
    """A filter's card by NavCB (``i`` — the direction, ``pg`` — the filter's index)."""
    return NavCB(s="fv", p=project.key, i=d, pg=f)


def _dir_fp(project: Project, d: int) -> str:
    dirs = status.project_info(project).directions
    return configedit.fingerprint(dirs[d]) if 0 <= d < len(dirs) else ""


def _entry(project: Project, c: FltCB) -> Any:
    """The tapped filter, or None if the list changed under the button."""
    data = status.project_info(project).data
    entries = configedit.filters_of(data, c.d)
    if not 0 <= c.f < len(entries) or (c.h and configedit.filter_fp(data, c.d, entries[c.f]) != c.h):
        return None
    return entries[c.f]


def _filter_cb(router_filter):
    """A filter editor's button (FltCB): its handler gets ``project`` loaded."""
    def register(handler):
        router.callback_query(router_filter)(with_project(FltCB)(handler))
        return handler
    return register


# ── the list (🧹 Фильтры / 🧹 Фильтры направления) ───────────────────────────


@view("flt")
@view("dflt")
async def filters_view(message: Message, edit: bool, nav: NavCB, *, project: Project, note: str = "",
                       **_) -> None:
    d = nav.i if nav.s == "dflt" else -1
    info = status.project_info(project)
    entries = configedit.filters_of(info.data, d)
    lines, own = [], []
    for n, f in enumerate(entries):
        args = configedit.filter_args(f)
        detail = "; ".join(f"{label(a.key)}: {_arg_text(a, info.names)}" for a in args if a.value is not None)
        lines.append(f"{n + 1}. {head(name_of(f))}"
                     + (f" — <i>{esc(detail)}</i>" if detail else ""))
        if info.writable:
            own.append([button(f"{n + 1}. {name_of(f)}",
                               FltCB(a="v", p=project.key, d=d, f=n, h=configedit.filter_fp(info.data, d, f)))])
    if info.writable:
        own.append([button(TITLES["flt_add"], FltCB(a="n", p=project.key, d=d, h=_dir_fp(project, d)))])
    more = "Фильтры срабатывают по очереди, сверху вниз."
    if not info.readable:
        scope = texts.unreadable(info)
    elif d < 0:
        scope = "Для всех направлений проекта, у которых нет своих."
        if mine := sum(1 for x in info.directions if x.get("filters")):
            scope += f" Направлений со своими фильтрами: <b>{mine}</b> (в карточке направления)."
        if not entries:
            scope += "\n\nФильтров нет — копируется всё как есть."
        more = "Фильтры решают, какие посты не копировать и что в них поменять. " + more
    else:
        scope = f"Свои фильтры направления № {d + 1}" + (
            "." if entries else " не заданы — действуют общие фильтры проекта. Если добавить сюда "
                                "фильтр, общие скопируются сюда же, и дальше у направления будет свой список.")
    hints = [("Фильтр из списка", "его настройки, порядок, удаление"),
             (TITLES["flt_add"], "выбрать из списка")] if info.writable else ()
    await show(message, edit, nav.s, project, body=scope + ("\n\n" + "\n".join(lines) if lines else ""),
               more=more, note=note, own=own, own_hints=hints, i=nav.i, pg=nav.pg)


# ── ➕ Добавить фильтр ───────────────────────────────────────────────────────


@_filter_cb(FltCB.filter(F.a == "n"))
async def on_new(callback: CallbackQuery, callback_data: FltCB, project: Project, state: FSMContext) -> None:
    c = callback_data
    if c.d >= 0 and _dir_fp(project, c.d) != c.h:
        await stale_tap(callback, texts.config_error("stale"))
        return
    # the ones that only drop posts first, under their subheading, then the ones that change them
    found = sorted(enumerate(filtercatalog.ADDABLE_FILTERS), key=lambda f: f[1] not in filtercatalog.EARLY_FILTERS)
    groups = []
    for heading, early in (("Отсеять посты", True), ("Изменить посты", False)):
        groups.append("\n".join([f"<i>{heading}</i>"] + [
            f"{head(filtercatalog.display_name(n))} — {esc(filtercatalog.ABOUT[n])}"
            for _, n in found if (n in filtercatalog.EARLY_FILTERS) == early]))
    options = [(filtercatalog.display_name(n), str(i)) for i, n in found]
    await start_form(
        callback, state, Input.value,
        f"{head(TITLES['flt_add'])} — " + ("для всего проекта" if c.d < 0 else f"направление № {c.d + 1}")
        + ". Какой?\n\n" + "\n\n".join(groups) + "\n\n" + texts.more(
            "Фильтры, которые только отсеивают посты, встанут в начало списка, остальные — в конец; "
            "порядок потом можно поменять."),
        _back(project, c.d), markup=choice_kb("flt_new", options), choice=True,
        data={"kind": "flt_new", "p": project.key, "d": c.d, "h": c.h},
    )


@router.callback_query(Input.value, ChoiceCB.filter(F.scope == "flt_new"))
async def on_new_pick(callback: CallbackQuery, callback_data: ChoiceCB, state: FSMContext,
                      store: ConfigStore, deps: dict) -> None:
    data = await state.get_data()
    n = int(callback_data.value) if callback_data.value.isdigit() else -1
    if data.get("kind") != "flt_new" or not 0 <= n < len(filtercatalog.ADDABLE_FILTERS):
        await stale_tap(callback)
        return
    if (project := await project_of(callback, data["p"])) is None:
        return
    await callback.answer()
    name = filtercatalog.ADDABLE_FILTERS[n]
    key = filtercatalog.REQUIRED_ARG.get(name)
    if key:
        kind = next(k for a, k, _ in filtercatalog.FILTER_ARGS[name] if a == key)
        await message_of(callback).edit_reply_markup(reply_markup=None)
        await ask(message_of(callback), state, Input.value,
                  f"{head('➕ ' + filtercatalog.display_name(name))}: {label(key)} — {_ask_text(name, key, kind)}",
                  kind="flt_new_items", name=name, arg_kind=kind)
        return
    await leave_form(callback.from_user.id, state)
    await _add(message_of(callback), True, project, data, name, None, store, deps)


@input_kind("flt_new")
async def new_typed(message: Message, **_) -> None:
    await message.answer(texts.USE_BUTTONS)


@input_kind("flt_new_items")
async def new_items(message: Message, state: FSMContext, raw: str, data: dict, project: Project,
                    store: ConfigStore, deps: dict, **_) -> None:
    items = configparse.parse_items(data["arg_kind"], raw)
    await leave_form(message.chat.id, state)
    await _add(message, False, project, data, data["name"], items, store, deps)


async def _add(message: Message, edit: bool, project: Project, data: dict, name: str, items,
               store: ConfigStore, deps: dict) -> None:
    d, copied = data["d"], []

    def mutate(cfg: Any) -> None:
        copied.append(configedit.add_filter(cfg, d, data["h"], name, items))

    def outcome(done: str) -> str:
        if copied and copied[0]:
            return f"{done}\nОбщие фильтры скопированы в список направления, новый добавлен к ним."
        return done

    await save(message, edit, project, lambda p: store.update(p, mutate), _back(project, d), deps, outcome=outcome)


# ── 🧹 Фильтр: one filter's card ────────────────────────────────────────────


def _value_text(a: configedit.FilterArg) -> str:
    if a.kind in filtercatalog.LIST_KINDS:
        return f"{len(a.value or [])} шт."
    if a.value is None:
        return "по умолчанию" if a.default in (None, "") else f"по умолчанию ({esc(a.default)})"
    if a.kind == "bool":
        return texts.on_off(bool(a.value))
    return f"<code>{esc(_short(a.value, 200))}</code>"


@view("fv")
async def filter_view(message: Message, edit: bool, nav: NavCB, *, project: Project, note: str = "",
                      **_) -> None:
    await show_filter(message, edit, project, FltCB(a="v", p=project.key, d=nav.i, f=nav.pg), note)


async def show_filter(message: Message, edit: bool, project: Project, c: FltCB, note: str = "") -> None:
    info = status.project_info(project)
    entry = _entry(project, c)
    if entry is None:
        await filters_view(message, edit, _back(project, c.d), project=project, note=texts.config_error("stale"))
        return
    name = configedit.filter_name(entry)
    args = configedit.filter_args(entry)
    base: dict[str, Any] = {"p": project.key, "d": c.d, "f": c.f, "h": configedit.filter_fp(info.data, c.d, entry)}
    # 🔬 Тонкая настройка: FltCB.n == 1 (not on ``x``, where n is an item's index)
    advanced = c.n == 1 and c.a != "x"
    mode = 1 if advanced else -1  # carried by ☑️ / 📝, so their card reopens the same
    hide = set() if advanced else {
        n for n, a in enumerate(args) if a.key in filtercatalog.ADVANCED_ARGS and a.value is None}
    lists = [n for n, a in enumerate(args) if a.kind in filtercatalog.LIST_KINDS]
    k = c.k if c.k in lists else (lists[0] if lists else -1)
    count = len(configedit.filters_of(info.data, c.d))
    lines = [f"{head(filtercatalog.display_name(name))} · " + ("для всего проекта" if c.d < 0 else f"направление № {c.d + 1}")
             + f" · № {c.f + 1} из {count}"]
    if name in filtercatalog.ABOUT:
        lines.append(esc(filtercatalog.ABOUT[name]))
    # the list opened below says its count itself
    lines += [f"• {esc(label(a.key))}: " + (_value_text(a) if a.kind else "<i>меняется только в файле</i>")
              for n, a in enumerate(args) if n not in hide and n != k]
    rows: list = []
    hints = []
    if k >= 0:
        key = args[k].key
        items = configedit.filter_items(entry, key)
        size = settings.FILTER_PAGE_SIZE
        page = c.pg % pages(len(items), size)
        shown = list(enumerate(items))[page * size:(page + 1) * size]
        kind, int_keys, names = args[k].kind, configedit.int_keys(entry, key), info.names
        lines.append(f"\n<b>{esc(label(key))}</b> — {len(items)} шт.:\n"
                     + ("\n".join(f"{n + 1}. {_item_html(item, kind, int_keys, names, key)}" for n, item in shown)
                        or "— пусто"))
        if key == "keywords" and any(_keyword(item) != item for item in items):
            lines.append(f"<i>{PATTERN_NOTE}</i>")
        if len(lists) > 1:
            rows.append([button(("• " if n == k else "") + label(args[n].key), FltCB(a="v", k=n, **base))
                         for n in lists])
        removes = [button(f"{ROW_REMOVE} {n + 1}. {_item_plain(item, kind, int_keys, names, key)}",
                          FltCB(a="x", k=k, n=n, pg=page, **base))
                   for n, item in enumerate(items)]
        rows += paged_rows(removes, page, size, lambda pg: FltCB(a="v", k=k, pg=pg, **base))
        rows.append([button(TITLES["items_add"], FltCB(a="+", k=k, **base))])
        hints += [(f"{ROW_REMOVE} значение", "убрать его из списка"), (TITLES["items_add"], "новые значения")]
    for n, a in enumerate(args):
        if n in hide:
            continue
        if a.kind == "bool":
            on = bool(a.default if a.value is None else a.value)
            row = [button(f"{CHECKED if on else UNCHECKED} {label(a.key)}", FltCB(a="t", k=n, n=mode, **base))]
            if configedit.bool_or_set(entry, a.key):
                row.append(button(TITLES["only_names"], FltCB(a="+", k=n, **base)))
            rows.append(row)
        elif a.kind in ("text", "number"):
            rows.append([button(f"📝 {label(a.key)}", FltCB(a="e", k=n, n=mode, **base))])
    if hide:
        rows.append([button(f"{TITLES['advanced']} ({len(hide)})", FltCB(a="v", n=1, k=c.k, **base))])
        hints.append((TITLES["advanced"], "редкие технические настройки — обычно их менять не нужно"))
    move = [button(TITLES[t], FltCB(a=act, **base)) for t, act, ok in (
        ("up", "u", c.f > 0), ("down", "w", c.f < count - 1)) if ok]
    rows += [move, [button(TITLES["flt_del"], FltCB(a="r", **base))]]
    visible = [a for n, a in enumerate(args) if n not in hide]
    # only what the card has: a hint for a button that isn't there confuses
    if any(a.kind == "bool" for a in visible):
        hints.append((f"{CHECKED} / {UNCHECKED}", "включить или выключить"))
    if any(a.kind in ("text", "number") for a in visible):
        hints.append(("📝 значение", "задать своё"))
    if move:
        hints.append((" / ".join(b.text for b in move), "порядок: фильтры срабатывают сверху вниз"))
    hints.append((TITLES["flt_del"], "убрать этот фильтр"))
    await show(message, edit, "fv", project, body="\n".join(lines), more=f"В файле настроек: <code>{esc(name)}</code>",
               note=note, own=rows,
               own_hints=hints, back=_back(project, c.d), parent="" if c.d < 0 else "dflt")


@_filter_cb(FltCB.filter(F.a == "v"))
async def on_view(callback: CallbackQuery, callback_data: FltCB, project: Project) -> None:
    await callback.answer()
    await show_filter(message_of(callback), True, project, callback_data)


async def _write(callback: CallbackQuery, project: Project, c: FltCB, mutate, store: ConfigStore, deps: dict,
                 *, card: FltCB) -> None:
    """A change of the filter's card, saved; ``card`` — the card to reopen."""
    await callback.answer()

    async def reopen(target: Message, done: str) -> None:
        await show_filter(target, True, project, card, done)

    await save(message_of(callback), True, project, lambda p: store.update(p, mutate), reopen, deps,
               back=_back(project, c.d))


def _arg_at(project: Project, c: FltCB, kinds: tuple):
    entry = _entry(project, c)
    args = configedit.filter_args(entry) if entry is not None else []
    if not 0 <= c.k < len(args) or args[c.k].kind not in kinds:
        return None, None
    return entry, args[c.k]


@_filter_cb(FltCB.filter(F.a == "x"))
async def on_remove(callback: CallbackQuery, callback_data: FltCB, project: Project, store: ConfigStore,
                    deps: dict) -> None:
    c = callback_data
    _, arg = _arg_at(project, c, filtercatalog.LIST_KINDS)
    if arg is None:
        await stale_tap(callback, texts.config_error("stale"))
        return
    await _write(callback, project, c, lambda cfg: configedit.remove_filter_item(cfg, c.d, c.f, c.h, arg.key, c.n),
                 store, deps, card=c.model_copy(update={"h": ""}))


@_filter_cb(FltCB.filter(F.a == "t"))
async def on_toggle(callback: CallbackQuery, callback_data: FltCB, project: Project, store: ConfigStore,
                    deps: dict) -> None:
    c = callback_data
    _, arg = _arg_at(project, c, ("bool",))
    if arg is None:
        await stale_tap(callback, texts.config_error("stale"))
        return
    on = bool(arg.default if arg.value is None else arg.value)
    await _write(callback, project, c, lambda cfg: configedit.set_filter_arg(cfg, c.d, c.f, c.h, arg.key, not on),
                 store, deps, card=c.model_copy(update={"h": ""}))


@_filter_cb(FltCB.filter(F.a.in_({"u", "w"})))
async def on_move(callback: CallbackQuery, callback_data: FltCB, project: Project, store: ConfigStore,
                  deps: dict) -> None:
    c = callback_data
    step = -1 if c.a == "u" else 1
    await _write(callback, project, c, lambda cfg: configedit.move_filter(cfg, c.d, c.f, c.h, step),
                 store, deps, card=c.model_copy(update={"f": c.f + step, "h": ""}))


@_filter_cb(FltCB.filter(F.a == "r"))
async def on_delete(callback: CallbackQuery, callback_data: FltCB, project: Project, state: FSMContext) -> None:
    c = callback_data
    entry = _entry(project, c)
    if entry is None:
        await stale_tap(callback, texts.config_error("stale"))
        return
    last = len(configedit.filters_of(status.project_info(project).data, c.d)) == 1
    tail = ("\n\nЭто последний свой фильтр направления — оно вернётся к общим." if last and c.d >= 0 else "")
    await ask_confirm(
        callback, state,
        f"{head(TITLES['flt_del'])} {head(name_of(entry))}?{tail}\n\n"
        f"Прошлую версию настроек можно вернуть: {title('cfg_undo')}.",
        "flt_del", _card(project, c.d, c.f), yes=YES_DELETE, p=project.key, cb=c.pack(),
    )


@confirmed("flt_del")
async def do_delete(callback: CallbackQuery, action: dict, project: Project, store: ConfigStore, deps: dict,
                    **_) -> None:
    c = FltCB.unpack(action["cb"])
    await callback.answer()
    await save(message_of(callback), True, project,
               lambda p: store.update(p, lambda cfg: configedit.delete_filter(cfg, c.d, c.f, c.h)),
               _back(project, c.d), deps)


# ── typed values: ➕ items of a list-like arg, 📝 a scalar ────────────────────


@_filter_cb(FltCB.filter(F.a.in_({"+", "e"})))
async def on_typed(callback: CallbackQuery, callback_data: FltCB, project: Project, state: FSMContext) -> None:
    c = callback_data
    kinds = filtercatalog.LIST_KINDS + ("bool",) if c.a == "+" else ("text", "number")
    entry, arg = _arg_at(project, c, kinds)
    if arg is None or (arg.kind == "bool" and not configedit.bool_or_set(entry, arg.key)):
        await stale_tap(callback, texts.config_error("stale"))
        return
    name = name_of(entry)
    current = "" if c.a == "+" else f", сейчас: {_value_text(arg)}"
    names = arg.kind == "bool"  # 📝 Только эти @…: the first names replace the bool
    await start_form(
        callback, state, Input.value,
        f"{head(('➕ ' if c.a == '+' else '📝 ') + name)}: {esc(label(arg.key))}{current} — "
        + (NAMES_ASK if names else _ask_text(entry, arg.key, arg.kind)),
        _card(project, c.d, c.f), markup=pick_kb() if arg.kind == "ids" else None,
        data={"kind": "filter_items" if c.a == "+" else "filter_value", "p": project.key, "cb": c.pack(),
              "arg": arg.key, "arg_kind": "set" if names else arg.kind,
              "int_keys": configedit.int_keys(entry, arg.key)},
    )


async def _typed_save(message: Message, state: FSMContext, data: dict, project: Project, mutate,
                      store: ConfigStore, deps: dict) -> None:
    c = FltCB.unpack(data["cb"])
    await leave_form(message.chat.id, state)

    async def reopen(target: Message, done: str) -> None:
        await show_filter(target, True, project, c.model_copy(update={"pg": 0, "h": ""}), done)

    await save(message, False, project, lambda p: store.update(p, lambda cfg: mutate(cfg, c)), reopen, deps,
               back=_back(project, c.d))


@input_kind("filter_items")
async def add_items(message: Message, state: FSMContext, raw: str, data: dict, project: Project,
                    store: ConfigStore, deps: dict, **_) -> None:
    items = configparse.parse_items(data["arg_kind"], raw, data.get("int_keys", False))
    await _typed_save(message, state, data, project,
                      lambda cfg, c: configedit.add_filter_items(cfg, c.d, c.f, c.h, data["arg"], items), store, deps)


@input_kind("filter_value")
async def set_value(message: Message, state: FSMContext, raw: str, data: dict, project: Project,
                    store: ConfigStore, deps: dict, **_) -> None:
    if raw == configparse.CLEAR:
        value = None
    elif data["arg_kind"] == "number":
        value = configparse.parse_number(raw)
    else:
        value = configparse.parse_text(raw)
    await _typed_save(message, state, data, project,
                      lambda cfg, c: configedit.set_filter_arg(cfg, c.d, c.f, c.h, data["arg"], value), store, deps)
