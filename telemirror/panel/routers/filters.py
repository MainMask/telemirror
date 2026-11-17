"""🧹 Фильтры: a project's filters (for directions without their own) and a
direction's own. Filters are added from ``configstore.FILTER_ARGS``, deleted,
moved; a filter's card edits its args — list-like ones item by item, scalars
by a toggle or a typed value. Every write goes through ``ConfigStore.update``,
so a value config.py refuses (a bad format, an empty keyword list) is refused
with its error and the file stays as it was."""

from collections.abc import Set as AbstractSet
from contextlib import suppress
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from telemirror.panel import configstore, settings, status, texts
from telemirror.panel.callbacks import ChoiceCB, FltCB, NavCB
from telemirror.panel.configstore import ConfigError, ConfigStore
from telemirror.panel.keyboards.common import button, choice_kb, pages
from telemirror.panel.registry import NEXT, PREV, YES_DELETE
from telemirror.panel.routers._common import (
    ask,
    ask_confirm,
    confirmed,
    input_kind,
    leave_form,
    message_of,
    project_of,
    stale_tap,
    start_form,
)
from telemirror.panel.screens import esc, head, show, view
from telemirror.panel.states import Input
from telemirror.panel.systemd import Systemd
from telemirror.panel.writes import save
from telemirror.projects import Project

router = Router(name="filters")

ABOUT = {
    "SkipWithKeywordsFilter": "не пересылать сообщения с этими словами",
    "AllowWithKeywordsFilter": "пересылать только сообщения с этими словами",
    "SkipWithUrlFilter": "не пересылать сообщения со ссылками на эти каналы",
    "SkipUrlFilter": "не пересылать сообщения с любыми ссылками",
    "SkipAllFilter": "не пересылать ничего",
    "UrlMessageFilter": "заменять ссылки в тексте заглушкой (только режим «копия»)",
    "KeywordReplaceFilter": "заменять слова в тексте (только режим «копия»)",
    "ForwardFormatFilter": "оформление: подпись с названием и ссылкой на источник",
    "MappedNameForwardFormat": "оформление с заданными именами каналов",
    "DocumentFilenameFilter": "переименовывать файлы-документы (только режим «копия»)",
    "WatermarkRemovalFilter": "убирать водяной знак источника и/или ставить свой (Linux, режим «копия»)",
    "RestrictSavingContentBypassFilter": "копировать медиа из источников с запретом копирования "
                                         "(после фильтра водяного знака)",
}
ARGS = {
    "keywords": "ключевые слова", "blacklist": "чёрный список", "whitelist": "белый список",
    "placeholder": "заглушка", "filter_mention": "убирать @упоминания",
    "filter_by_id_mention": "убирать упоминания по ID", "skip_mention": "и с @упоминаниями",
    "format": "формат", "mapped": "имена каналов", "suffix": "суффикс", "remove": "убирать из имени",
    "remove_watermark": "убирать знак источника", "stamp_watermark": "ставить свой знак",
    "template_path": "шаблон знака (путь на сервере)", "match_threshold": "порог распознавания",
    "channels": "только для источников",
    "scale_min": "поиск знака: мин. масштаб", "scale_max": "поиск знака: макс. масштаб",
    "scale_steps": "поиск знака: шагов масштаба", "inpaint_dilate_px": "расширение области знака, px",
    "stamp_watermark_path": "свой знак (путь на сервере)", "stamp_opacity": "свой знак: прозрачность",
    "stamp_scale": "свой знак: размер", "stamp_video_max_duration_s": "видео со знаком: макс. длина, с",
    "stamp_video_preset": "видео: пресет x264", "stamp_video_crf": "видео: качество (CRF)",
    "stamp_video_max_encode_s": "видео: макс. время кодирования, с",
    "stamp_video_encode_realtime_ratio": "видео: скорость кодирования к реальному времени",
    "max_concurrent_video_encodes": "видео: кодировать одновременно",
}
NAMES_ASK = ("пришлите @имена, которые убирать (остальные упоминания останутся), по одному на строку — "
             "как в тексте, с <code>@</code>.")
ASK = {
    "set": "пришлите значения, по одному на строку.",
    "list": "пришлите значения, по одному на строку.",
    "ids": "пришлите ID каналов через запятую или с новой строки.",
    "map": "пришлите пары по одной на строку: <code>что =&gt; на что</code>.",
    "text": "пришлите новое значение или <code>-</code>, чтобы вернуть значение по умолчанию.",
    "number": "пришлите число или <code>-</code>, чтобы вернуть значение по умолчанию.",
}
KEYWORD_HINT = " Слово можно задать регулярным выражением: <code>r'шаблон'</code>."
FORMAT_HINT = (" Обязательно <code>{message_text}</code>; можно <code>{channel_name}</code>, "
               "<code>{message_link}</code>, <code>{sender_title}</code>, <code>{sender_username}</code>.")


def label(key: str) -> str:
    return ARGS.get(key, key)


def _short(value: Any, limit: int = 60) -> str:
    if isinstance(value, AbstractSet):  # incl. ruamel's CommentedSet (a !!set)
        value = sorted(str(v) for v in value)
    if isinstance(value, dict):
        value = [f"{k} => {v}" for k, v in value.items()]
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(v) for v in value)
    text = str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _ask_text(entry: Any, key: str, kind: str) -> str:
    text = ASK[kind]
    if key == "keywords" and kind != "map":
        text += KEYWORD_HINT
    if key == "format":
        text += FORMAT_HINT
    if configstore.int_keys(entry, key):
        text = "пришлите пары по одной на строку: <code>-1001234567890 =&gt; Имя канала</code>."
    return text


def _back(project: Project, d: int) -> NavCB:
    return NavCB(s="flt", p=project.key) if d < 0 else NavCB(s="dflt", p=project.key, i=d)


def _dir_fp(project: Project, d: int) -> str:
    dirs = status.project_info(project).directions
    return configstore.fingerprint(dirs[d]) if 0 <= d < len(dirs) else ""


def _entry(project: Project, c: FltCB) -> Any:
    """The tapped filter, or None if the list changed under the button."""
    entries = configstore.filters_of(status.project_info(project).data, c.d)
    if not 0 <= c.f < len(entries) or (c.h and configstore.fingerprint(entries[c.f]) != c.h):
        return None
    return entries[c.f]


# ── the list (🧹 Фильтры / 🧹 Фильтры направления) ───────────────────────────


@view("flt")
@view("dflt")
async def filters_view(message: Message, edit: bool, nav: NavCB, state: FSMContext, note: str = "", **_) -> None:
    project = status.find(nav.p)
    if project is None:
        await message.answer(texts.NO_PROJECT)
        return
    await show_filters(message, edit, project, nav.i if nav.s == "dflt" else -1, note)


async def show_filters(message: Message, edit: bool, project: Project, d: int, note: str = "") -> None:
    info = status.project_info(project)
    entries = configstore.filters_of(info.data, d)
    lines, own = [], []
    for n, f in enumerate(entries):
        args = configstore.filter_args(f)
        detail = "; ".join(f"{a.key}: {_short(a.value)}" for a in args if a.value is not None)
        lines.append(f"{n + 1}. {head(configstore.filter_name(f))}"
                     + (f" — <code>{esc(detail)}</code>" if detail else ""))
        if info.writable:
            own.append([button(f"✏️ {n + 1}. {configstore.filter_name(f)}",
                               FltCB(a="v", p=project.key, d=d, f=n, h=configstore.fingerprint(f)))])
    if info.writable:
        own.append([button("➕ Добавить фильтр", FltCB(a="n", p=project.key, d=d, h=_dir_fp(project, d)))])
    if d < 0:
        scope = "Общие фильтры — для направлений без своих. Работают по порядку, сверху вниз."
        if mine := sum(1 for x in info.directions if x.get("filters")):
            scope += f" Направлений со своими: <b>{mine}</b> (в карточке направления)."
    else:
        scope = f"Свои фильтры направления № {d + 1}" + (
            "." if entries else " не заданы — действуют общие. Первый добавленный сюда фильтр "
                                "добавится к копии общих: свой список заменяет их.")
    body = scope + ("\n\n" + "\n".join(lines) if lines else "")
    hints = [("✏️ фильтр", "его значения, порядок, удаление"),
             ("➕ Добавить фильтр", "выбрать из списка доступных")] if info.writable else ()
    screen = "flt" if d < 0 else "dflt"
    await show(message, edit, screen, project, body=body, note=note, own=own, own_hints=hints, i=d,
               back=None if d < 0 else NavCB(s="dir", p=project.key, i=d))


# ── ➕ Добавить фильтр ───────────────────────────────────────────────────────


@router.callback_query(FltCB.filter(F.a == "n"))
async def on_new(callback: CallbackQuery, callback_data: FltCB, state: FSMContext) -> None:
    c = callback_data
    project = await project_of(callback, c.p)
    if project is None:
        return
    if c.d >= 0 and _dir_fp(project, c.d) != c.h:
        await stale_tap(callback, texts.config_error("stale"))
        return
    lines = "\n".join(f"{head(n)} — {esc(ABOUT[n])}" for n in configstore.ADDABLE_FILTERS)
    options = [(n, str(i)) for i, n in enumerate(configstore.ADDABLE_FILTERS)]
    await start_form(
        callback, state, Input.value,
        f"{head('➕ Добавить фильтр')} — " + ("общий" if c.d < 0 else f"направление № {c.d + 1}")
        + f". Какой?\n\n{lines}\n\n<i>Фильтры, которые только отбрасывают сообщения, встанут в начало "
        "списка, остальные — в конец; порядок потом можно поменять.</i>",
        _back(project, c.d), markup=choice_kb("flt_new", options), choice=True,
        data={"kind": "flt_new", "p": project.key, "d": c.d, "h": c.h},
    )


@router.callback_query(Input.value, ChoiceCB.filter(F.scope == "flt_new"))
async def on_new_pick(callback: CallbackQuery, callback_data: ChoiceCB, state: FSMContext,
                      store: ConfigStore, sysd: Systemd) -> None:
    data = await state.get_data()
    n = int(callback_data.value) if callback_data.value.isdigit() else -1
    if data.get("kind") != "flt_new" or not 0 <= n < len(configstore.ADDABLE_FILTERS):
        await stale_tap(callback)
        return
    await callback.answer()
    name = configstore.ADDABLE_FILTERS[n]
    key = configstore.REQUIRED_ARG.get(name)
    if key:
        kind = next(k for a, k, _ in configstore.FILTER_ARGS[name] if a == key)
        with suppress(Exception):
            await message_of(callback).edit_reply_markup(reply_markup=None)
        await ask(message_of(callback), state, Input.value,
                  f"{head('➕ ' + name)}: {label(key)} — {_ask_text(name, key, kind)}",
                  kind="flt_new_items", name=name, arg_kind=kind)
        return
    project = status.find(data["p"])
    await leave_form(callback.from_user.id, state)
    if project is None:
        await stale_tap(callback, texts.NO_PROJECT)
        return
    await _add(message_of(callback), True, project, data, name, None, store, sysd)


@input_kind("flt_new")
async def new_typed(message: Message, state: FSMContext, raw: str, data: dict, **_) -> None:
    await message.answer("Выберите фильтр кнопкой выше — или /cancel, чтобы выйти.")


@input_kind("flt_new_items")
async def new_items(message: Message, state: FSMContext, raw: str, data: dict, store: ConfigStore,
                    sysd: Systemd, **_) -> None:
    try:
        items = configstore.parse_items(data["arg_kind"], raw)
    except ConfigError as e:
        await message.answer(f"{texts.config_error(e.code, e.detail)}\nПришлите ещё раз:")
        return
    project = status.find(data["p"])
    await leave_form(message.chat.id, state)
    if project is None:
        await message.answer(texts.NO_PROJECT)
        return
    await _add(message, False, project, data, data["name"], items, store, sysd)


async def _add(message: Message, edit: bool, project: Project, data: dict, name: str, items, store: ConfigStore,
               sysd: Systemd) -> None:
    d, copied = data["d"], []

    def mutate(cfg: Any) -> None:
        copied.append(configstore.add_filter(cfg, d, data["h"], name, items))

    async def after(target: Message, done: str) -> None:
        if copied and copied[0]:
            done = f"{done}\nОбщие фильтры скопированы в свой список направления, новый добавлен к ним."
        await show_filters(target, True, project, d, done)

    await save(message, edit, project, lambda p: store.update(p, mutate), after, _back(project, d), sysd)


# ── 🧹 Фильтр: one filter's card ────────────────────────────────────────────


def _value_text(a: configstore.FilterArg) -> str:
    if a.kind in configstore.LIST_KINDS:
        return f"{len(a.value or [])} шт."
    if a.value is None:
        return "по умолчанию" if a.default in (None, "") else f"по умолчанию ({esc(a.default)})"
    if a.kind == "bool":
        return texts.on_off(bool(a.value))
    return f"<code>{esc(_short(a.value, 200))}</code>"


async def show_filter(message: Message, edit: bool, project: Project, c: FltCB, note: str = "") -> None:
    info = status.project_info(project)
    entry = _entry(project, c)
    if entry is None:
        await show_filters(message, edit, project, c.d, texts.config_error("stale"))
        return
    name = configstore.filter_name(entry)
    args = configstore.filter_args(entry)
    fp = configstore.fingerprint(entry)
    base: dict[str, Any] = {"p": project.key, "d": c.d, "f": c.f, "h": fp}
    lists = [n for n, a in enumerate(args) if a.kind in configstore.LIST_KINDS]
    k = c.k if c.k in lists else (lists[0] if lists else -1)
    count = len(configstore.filters_of(info.data, c.d))
    lines = [f"{head(name)} · " + ("общий" if c.d < 0 else f"направление № {c.d + 1}") + f" · № {c.f + 1} из {count}"]
    if name in ABOUT:
        lines.append(esc(ABOUT[name]))
    lines += [f"• {esc(label(a.key))}: " + (_value_text(a) if a.kind else "<i>правится в файле</i>") for a in args]
    rows, hints = [], []
    if k >= 0:
        key = args[k].key
        items = configstore.filter_items(entry, key)
        size = settings.FILTER_PAGE_SIZE
        pg_count = pages(len(items), size)
        page = c.pg % pg_count
        shown = list(enumerate(items))[page * size:(page + 1) * size]
        lines.append(f"\n<b>{esc(label(key))}</b> — {len(items)} шт.:\n"
                     + ("\n".join(f"{n + 1}. <code>{esc(item)}</code>" for n, item in shown) or "— пусто"))
        if len(lists) > 1:
            rows.append([button(("• " if n == k else "") + label(args[n].key), FltCB(a="v", k=n, **base))
                         for n in lists])
        if info.writable:
            rows += [[button(f"✖️ {n + 1}. {item[:40]}", FltCB(a="x", k=k, n=n, pg=page, **base))]
                     for n, item in shown]
        if pg_count > 1:
            rows.append([button(PREV, FltCB(a="v", k=k, pg=(page - 1) % pg_count, **base)),
                         button(f"📄 {page + 1}/{pg_count}", FltCB(a="v", k=k, pg=page, **base)),
                         button(NEXT, FltCB(a="v", k=k, pg=(page + 1) % pg_count, **base))])
        if info.writable:
            rows.append([button("➕ Добавить", FltCB(a="+", k=k, **base))])
            hints += [("✖️ значение", "убрать его из списка"), ("➕ Добавить", "новые значения")]
    if info.writable:
        for n, a in enumerate(args):
            if a.kind == "bool":
                on = bool(a.default if a.value is None else a.value)
                row = [button(f"{'☑️' if on else '⬜'} {label(a.key)}", FltCB(a="t", k=n, **base))]
                if configstore.bool_or_set(entry, a.key):
                    row.append(button("📝 только эти @…", FltCB(a="+", k=n, **base)))
                rows.append(row)
            elif a.kind in ("text", "number"):
                rows.append([button(f"📝 {label(a.key)}", FltCB(a="e", k=n, **base))])
        move = [button(t, FltCB(a=act, **base)) for t, act, ok in (
            ("⬆️ Выше", "u", c.f > 0), ("⬇️ Ниже", "w", c.f < count - 1)) if ok]
        rows += [move, [button("🗑 Удалить фильтр", FltCB(a="r", **base))]]
        hints += [("☑️ / ⬜", "включить или выключить"), ("📝 значение", "задать своё"),
                  ("⬆️ / ⬇️", "порядок: фильтры работают сверху вниз")]
    await show(message, edit, "fv", project, body="\n".join(lines), note=note, own=rows,
               own_hints=hints, back=_back(project, c.d))


@router.callback_query(FltCB.filter(F.a == "v"))
async def on_view(callback: CallbackQuery, callback_data: FltCB) -> None:
    project = await project_of(callback, callback_data.p)
    if project is not None:
        await callback.answer()
        await show_filter(message_of(callback), True, project, callback_data)


async def _write(callback: CallbackQuery, project: Project, c: FltCB, mutate, store: ConfigStore, sysd: Systemd,
                 to_list: bool = False) -> None:
    await callback.answer()

    async def after(target: Message, done: str) -> None:
        if to_list:
            await show_filters(target, True, project, c.d, done)
        else:
            await show_filter(target, True, project, c.model_copy(update={"h": ""}), done)

    await save(message_of(callback), True, project, lambda p: store.update(p, mutate), after, _back(project, c.d), sysd)


def _arg_at(project: Project, c: FltCB, kinds: tuple):
    entry = _entry(project, c)
    args = configstore.filter_args(entry) if entry is not None else []
    if not 0 <= c.k < len(args) or args[c.k].kind not in kinds:
        return None, None
    return entry, args[c.k]


@router.callback_query(FltCB.filter(F.a == "x"))
async def on_remove(callback: CallbackQuery, callback_data: FltCB, store: ConfigStore, sysd: Systemd) -> None:
    c = callback_data
    project = await project_of(callback, c.p)
    if project is None:
        return
    _, arg = _arg_at(project, c, configstore.LIST_KINDS)
    if arg is None:
        await stale_tap(callback, texts.config_error("stale"))
        return
    await _write(callback, project, c,
                 lambda cfg: configstore.remove_filter_item(cfg, c.d, c.f, c.h, arg.key, c.n), store, sysd)


@router.callback_query(FltCB.filter(F.a == "t"))
async def on_toggle(callback: CallbackQuery, callback_data: FltCB, store: ConfigStore, sysd: Systemd) -> None:
    c = callback_data
    project = await project_of(callback, c.p)
    if project is None:
        return
    _, arg = _arg_at(project, c, ("bool",))
    if arg is None:
        await stale_tap(callback, texts.config_error("stale"))
        return
    on = bool(arg.default if arg.value is None else arg.value)
    await _write(callback, project, c,
                 lambda cfg: configstore.set_filter_arg(cfg, c.d, c.f, c.h, arg.key, not on), store, sysd)


@router.callback_query(FltCB.filter(F.a.in_({"u", "w"})))
async def on_move(callback: CallbackQuery, callback_data: FltCB, store: ConfigStore, sysd: Systemd) -> None:
    c = callback_data
    project = await project_of(callback, c.p)
    if project is None:
        return
    step = -1 if c.a == "u" else 1
    moved = c.model_copy(update={"f": c.f + step, "h": ""})

    async def after(target: Message, done: str) -> None:
        await show_filter(target, True, project, moved, done)

    await callback.answer()
    await save(message_of(callback), True, project,
               lambda p: store.update(p, lambda cfg: configstore.move_filter(cfg, c.d, c.f, c.h, step)),
               after, _back(project, c.d), sysd)


@router.callback_query(FltCB.filter(F.a == "r"))
async def on_delete(callback: CallbackQuery, callback_data: FltCB, state: FSMContext) -> None:
    c = callback_data
    project = await project_of(callback, c.p)
    if project is None:
        return
    entry = _entry(project, c)
    if entry is None:
        await stale_tap(callback, texts.config_error("stale"))
        return
    last = len(configstore.filters_of(status.project_info(project).data, c.d)) == 1
    tail = ("\n\nЭто последний свой фильтр направления — оно вернётся к общим." if last and c.d >= 0 else "")
    await ask_confirm(
        callback, state,
        f"{head('🗑 Удалить фильтр')} {head(configstore.filter_name(entry))}?{tail}\n\n"
        "Перед записью создаётся копия .bak.",
        "flt_del", NavCB(s="flt", p=project.key) if c.d < 0 else NavCB(s="dflt", p=project.key, i=c.d),
        yes=YES_DELETE, cb=c.pack(),
    )


@confirmed("flt_del")
async def do_delete(callback: CallbackQuery, action: dict, state: FSMContext, store: ConfigStore, sysd: Systemd,
                    **_) -> None:
    c = FltCB.unpack(action["cb"])
    project = await project_of(callback, c.p)
    if project is None:
        return
    await _write(callback, project, c, lambda cfg: configstore.delete_filter(cfg, c.d, c.f, c.h), store, sysd,
                 to_list=True)


# ── typed values: ➕ items of a list-like arg, 📝 a scalar ────────────────────


@router.callback_query(FltCB.filter(F.a.in_({"+", "e"})))
async def on_typed(callback: CallbackQuery, callback_data: FltCB, state: FSMContext) -> None:
    c = callback_data
    project = await project_of(callback, c.p)
    if project is None:
        return
    kinds = configstore.LIST_KINDS + ("bool",) if c.a == "+" else ("text", "number")
    entry, arg = _arg_at(project, c, kinds)
    if arg is None or (arg.kind == "bool" and not configstore.bool_or_set(entry, arg.key)):
        await stale_tap(callback, texts.config_error("stale"))
        return
    name = configstore.filter_name(entry)
    current = "" if c.a == "+" else f", сейчас: {_value_text(arg)}"
    names = arg.kind == "bool"  # 📝 только эти @…: the first names replace the bool
    await start_form(
        callback, state, Input.value,
        f"{head(('➕ ' if c.a == '+' else '📝 ') + name)}: {esc(label(arg.key))}{current} — "
        + (NAMES_ASK if names else _ask_text(entry, arg.key, arg.kind)),
        _back(project, c.d),
        data={"kind": "filter_items" if c.a == "+" else "filter_value", "p": project.key, "cb": c.pack(),
              "arg": arg.key, "arg_kind": "set" if names else arg.kind,
              "int_keys": configstore.int_keys(entry, arg.key)},
    )


async def _typed_save(message: Message, state: FSMContext, data: dict, mutate, store: ConfigStore,
                      sysd: Systemd) -> None:
    c = FltCB.unpack(data["cb"])
    project = status.find(data["p"])
    await leave_form(message.chat.id, state)
    if project is None:
        await message.answer(texts.NO_PROJECT)
        return

    async def after(target: Message, done: str) -> None:
        await show_filter(target, True, project, c.model_copy(update={"pg": 0, "h": ""}), done)

    await save(message, False, project, lambda p: store.update(p, lambda cfg: mutate(cfg, c)), after,
               _back(project, c.d), sysd)


@input_kind("filter_items")
async def add_items(message: Message, state: FSMContext, raw: str, data: dict, store: ConfigStore,
                    sysd: Systemd, **_) -> None:
    try:
        items = configstore.parse_items(data["arg_kind"], raw, data.get("int_keys", False))
    except ConfigError as e:
        await message.answer(f"{texts.config_error(e.code, e.detail)}\nПришлите ещё раз:")
        return
    await _typed_save(message, state, data,
                      lambda cfg, c: configstore.add_filter_items(cfg, c.d, c.f, c.h, data["arg"], items), store, sysd)


@input_kind("filter_value")
async def set_value(message: Message, state: FSMContext, raw: str, data: dict, store: ConfigStore,
                    sysd: Systemd, **_) -> None:
    try:
        if raw == configstore.CLEAR:
            value = None
        elif data["arg_kind"] == "number":
            value = configstore.parse_number(raw)
        else:
            value = configstore.parse_text(raw)
    except ConfigError as e:
        await message.answer(f"{texts.config_error(e.code, e.detail)}\nПришлите ещё раз:")
        return
    await _typed_save(message, state, data,
                      lambda cfg, c: configstore.set_filter_arg(cfg, c.d, c.f, c.h, data["arg"], value), store, sysd)
