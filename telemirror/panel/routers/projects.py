"""📁 Проекты: mirror configurations, their directions, filters and params."""

import logging
from contextlib import suppress
from typing import Any, Callable, Optional

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.callback_answer import CallbackAnswer

from telemirror.panel import configstore, keyboards, settings, status, texts
from telemirror.panel.callbacks import Act, Nav
from telemirror.panel.configstore import ConfigError, ConfigStore
from telemirror.panel.settings import Project
from telemirror.panel.systemd import Systemd
from telemirror.panel.ui import Panel, Screen, show

logger = logging.getLogger(__name__)
router = Router(name="projects")


class AddDirection(StatesGroup):
    source = State()
    targets = State()
    choice = State()  # mode / history / summary — answered with buttons


def _title(project: Project) -> str:
    return texts.PROJECT_TITLES[project.key]


def _filter_name(f: Any) -> str:
    return str(next(iter(f))) if isinstance(f, dict) and f else str(f)


def _short(value: Any, limit: int = 60) -> str:
    if isinstance(value, (set, frozenset)):
        value = sorted(str(v) for v in value)
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(v) for v in value)
    text = str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _effective(d: Any, data: Any) -> tuple[str, bool, bool]:
    """(mode, edits forwarded, deletes forwarded), direction over global."""
    mode = str(d.get("mode", data.get("mode", "copy")))
    edit_on = not bool(d.get("disable_edit", data.get("disable_edit", False)))
    delete_on = not bool(d.get("disable_delete", data.get("disable_delete", False)))
    return mode, edit_on, delete_on


def _history(pm: Any) -> str:
    if not isinstance(pm, dict) or not pm:
        return texts.HISTORY_NONE
    if pm.get("full_history"):
        return texts.HISTORY_FULL
    if pm.get("last_n") is not None:
        return texts.HISTORY_LAST_N.format(n=texts.esc(pm["last_n"]))
    if pm.get("since_date") is not None:
        return texts.HISTORY_SINCE.format(date=texts.esc(pm["since_date"]))
    return texts.HISTORY_NONE


def _chats(info: status.ProjectInfo, side: str) -> int:
    chats = set()
    for d in info.directions:
        for ref in d.get(side) or []:
            with suppress(ValueError):
                chats.add(configstore.chat_of(configstore.ref_str(ref)))
    return len(chats)


def _display_path(project: Project) -> str:
    try:
        return str(project.path.relative_to(settings.REPO_DIR))
    except ValueError:
        return str(project.path)


def _not_found() -> Screen:
    return texts.NOT_FOUND, keyboards.back(Nav(s="prj"), texts.BTN_TO_PROJECTS)


# ── screens ─────────────────────────────────────────────────────────────────


async def projects_screen(sysd: Systemd) -> Screen:
    items = []
    for project in status.visible_projects():
        info = status.project_info(project)
        st = await status.unit_state(sysd, project.unit_key)
        count = len(info.directions) if info.readable else None
        items.append((project.key, texts.project_button(_title(project), count, st.active if st else None)))
    text = texts.PROJECTS_TITLE + ("" if items else texts.PROJECTS_EMPTY)
    return text, keyboards.projects_list(items)


async def project_screen(sysd: Systemd, key: str) -> Screen:
    project = status.project_by_key(key)
    if project is None:
        return _not_found()
    info = status.project_info(project)
    st = await status.unit_state(sysd, project.unit_key)
    active = st.active if st else None
    state = texts.mirror_state(active) if project.live else texts.task_state(active)
    readable = info.readable
    text = texts.PROJECT_CARD.format(
        title=_title(project),
        descr=texts.PROJECT_DESCR[project.key],
        path=texts.esc(_display_path(project)),
        unit=settings.UNITS[project.unit_key],
        state=f"{texts.state_icon(active)} {state}",
        count=len(info.directions) if readable else texts.UNKNOWN_COUNT,
        sources=_chats(info, "from") if readable else texts.UNKNOWN_COUNT,
        targets=_chats(info, "to") if readable else texts.UNKNOWN_COUNT,
    )
    if info.read_only:
        text += "\n\n" + texts.READ_ONLY[info.read_only]
    if info.error:
        text += "\n\n" + texts.LOAD_ERROR.format(error=texts.esc(info.error[:300]))
    if (
        project.live
        and info.snapshot is not None
        and st is not None
        and st.running
        and st.since is not None
        and info.snapshot.mtime > st.since
    ):
        text += "\n\n" + texts.UNAPPLIED
    markup = keyboards.project_card(
        project.key, project.live, readable, bool(st and st.running), sysd.available
    )
    return text, markup


def directions_screen(key: str, page: int) -> Screen:
    project = status.project_by_key(key)
    if project is None:
        return _not_found()
    info = status.project_info(project)
    if not info.readable:
        return project_card_fallback(key)
    dirs = info.directions
    pages = max(1, -(-len(dirs) // settings.PAGE_SIZE))
    page = min(max(page, 0), pages - 1)
    start = page * settings.PAGE_SIZE
    lines, items = [], []
    for idx in range(start, min(start + settings.PAGE_SIZE, len(dirs))):
        d = dirs[idx]
        sources, targets = list(d.get("from") or []), list(d.get("to") or [])
        mode, edit_on, delete_on = _effective(d, info.data)
        marks = [
            texts.MARK_FORWARD if mode == "forward" else "",
            texts.MARK_HISTORY if d.get("past_mode") else "",
            texts.MARK_FILTERS if d.get("filters") else "",
            "" if edit_on else texts.MARK_NO_EDIT,
            "" if delete_on else texts.MARK_NO_DELETE,
        ]
        suffix = " · ".join(m for m in marks if m)
        lines.append(
            f"<b>{idx + 1}.</b> {texts.refs(sources)} → {texts.refs(targets)}"
            + (f" · <i>{suffix}</i>" if suffix else "")
        )
        items.append(
            (idx, f"{idx + 1}. {texts.short_refs(sources)} → {texts.short_refs(targets)}")
        )
    text = texts.DIRECTIONS_TITLE.format(
        project=_title(project), page=page + 1, pages=pages, count=len(dirs)
    )
    text += ("\n\n" + "\n".join(lines)) if lines else texts.DIRECTIONS_EMPTY
    return text, keyboards.directions_list(key, page, pages, items, info.writable)


def project_card_fallback(key: str) -> Screen:
    return texts.NOT_FOUND, keyboards.back(Nav(s="pc", p=key), texts.BTN_TO_PROJECT)


def direction_screen(key: str, page: int, idx: int) -> Screen:
    project = status.project_by_key(key)
    if project is None:
        return _not_found()
    info = status.project_info(project)
    dirs = info.directions
    if not 0 <= idx < len(dirs):
        return texts.NOT_FOUND, keyboards.back(Nav(s="dl", p=key, pg=page), texts.BTN_TO_LIST)
    d, data = dirs[idx], info.data
    mode, edit_on, delete_on = _effective(d, data)
    own = d.get("filters")
    text = texts.DIRECTION_CARD.format(
        n=idx + 1,
        project=_title(project),
        sources=texts.refs(d.get("from") or []),
        targets=texts.refs(d.get("to") or []),
        mode=texts.esc(mode),
        mode_src="" if "mode" in d else texts.FROM_GLOBAL,
        edit=texts.FORWARDED if edit_on else texts.NOT_FORWARDED,
        edit_src="" if "disable_edit" in d else texts.FROM_GLOBAL,
        delete=texts.FORWARDED if delete_on else texts.NOT_FORWARDED,
        delete_src="" if "disable_delete" in d else texts.FROM_GLOBAL,
        history=_history(d.get("past_mode")),
        filters=", ".join(texts.esc(_filter_name(f)) for f in own) if own else texts.FILTERS_GLOBAL,
    )
    markup = keyboards.direction_card(
        key, page, idx, configstore.fingerprint(d), edit_on, delete_on, info.writable
    )
    return text, markup


def filters_screen(key: str) -> Screen:
    project = status.project_by_key(key)
    if project is None:
        return _not_found()
    info = status.project_info(project)
    lines = []
    for n, f in enumerate(info.data.get("filters") or [], start=1):
        args = next(iter(f.values()), None) if isinstance(f, dict) else None
        detail = (
            "; ".join(f"{k}: {_short(v)}" for k, v in args.items())
            if isinstance(args, dict)
            else ""
        )
        lines.append(
            f"{n}. <b>{texts.esc(_filter_name(f))}</b>"
            + (f" — <code>{texts.esc(detail)}</code>" if detail else "")
        )
    own = sum(1 for d in info.directions if d.get("filters"))
    text = texts.FILTERS_TITLE.format(
        project=_title(project), filters="\n".join(lines) or texts.FILTERS_NONE
    )
    text += texts.FILTERS_OWN.format(n=own) + texts.FILTERS_HINT
    return text, keyboards.back(Nav(s="pc", p=key), texts.BTN_TO_PROJECT)


def params_screen(key: str) -> Screen:
    project = status.project_by_key(key)
    if project is None:
        return _not_found()
    info = status.project_info(project)
    data = info.data
    edit_on = not bool(data.get("disable_edit", False))
    delete_on = not bool(data.get("disable_delete", False))
    mode = str(data.get("mode", "copy"))
    text = texts.PARAMS_TITLE.format(
        project=_title(project),
        edit=texts.on_off(edit_on),
        delete=texts.on_off(delete_on),
        mode=texts.esc(mode),
    )
    return text, keyboards.params(key, edit_on, delete_on, mode, info.writable)


# ── navigation handlers ─────────────────────────────────────────────────────


@router.callback_query(Nav.filter(F.s == "prj"))
async def on_projects(callback: CallbackQuery, bot: Bot, panel: Panel, sysd: Systemd) -> None:
    await show(callback, bot, panel, await projects_screen(sysd))


@router.callback_query(Nav.filter(F.s == "pc"))
async def on_project(
    callback: CallbackQuery, callback_data: Nav, bot: Bot, panel: Panel, sysd: Systemd
) -> None:
    await show(callback, bot, panel, await project_screen(sysd, callback_data.p))


@router.callback_query(Nav.filter(F.s == "dl"))
async def on_directions(callback: CallbackQuery, callback_data: Nav, bot: Bot, panel: Panel) -> None:
    await show(callback, bot, panel, directions_screen(callback_data.p, callback_data.pg))


@router.callback_query(Nav.filter(F.s == "dc"))
async def on_direction(callback: CallbackQuery, callback_data: Nav, bot: Bot, panel: Panel) -> None:
    await show(callback, bot, panel, direction_screen(callback_data.p, callback_data.pg, callback_data.i))


@router.callback_query(Nav.filter(F.s == "flt"))
async def on_filters(callback: CallbackQuery, callback_data: Nav, bot: Bot, panel: Panel) -> None:
    await show(callback, bot, panel, filters_screen(callback_data.p))


@router.callback_query(Nav.filter(F.s == "par"))
async def on_params(callback: CallbackQuery, callback_data: Nav, bot: Bot, panel: Panel) -> None:
    await show(callback, bot, panel, params_screen(callback_data.p))


# ── writes ──────────────────────────────────────────────────────────────────


async def _write(
    callback: CallbackQuery,
    callback_answer: CallbackAnswer,
    bot: Bot,
    panel: Panel,
    store: ConfigStore,
    key: str,
    mutate: Callable[[Any], None],
    after: Callable[[], Screen],
    error_back: Nav,
) -> bool:
    """Validate + write, then render ``after`` (or the error). True on success."""
    project = status.project_by_key(key)
    if project is None:
        await show(callback, bot, panel, _not_found())
        return False
    # Validation imports config.py in a subprocess — seconds; say so first.
    await show(callback, bot, panel, (texts.VALIDATING, None))
    try:
        await store.update(project, mutate)
    except ConfigError as e:
        logger.warning("panel: config write to %s refused: %s", project.path.name, e)
        await show(
            callback, bot, panel,
            (texts.config_error(e.code, e.detail), keyboards.back(error_back)),
        )
        return False
    logger.info(
        "panel: %s updated by admin %s", project.path.name, callback.from_user.id
    )
    callback_answer.text = texts.SAVED[project.key]
    await show(callback, bot, panel, after())
    return True


@router.callback_query(Act.filter(F.a.in_({"te", "td", "dd"})))
async def on_direction_action(
    callback: CallbackQuery, callback_data: Act, callback_answer: CallbackAnswer,
    bot: Bot, panel: Panel, store: ConfigStore,
) -> None:
    data = callback_data
    back = Nav(s="dl", p=data.p, pg=data.pg)
    if data.a == "dd" and not data.ok:
        project = status.project_by_key(data.p)
        dirs = status.project_info(project).directions if project else []
        if not 0 <= data.i < len(dirs) or configstore.fingerprint(dirs[data.i]) != data.h:
            await show(callback, bot, panel, (texts.config_error("stale", ""), keyboards.back(back)))
            return
        d = dirs[data.i]
        text = texts.CONFIRM_DELETE_DIRECTION.format(
            n=data.i + 1, sources=texts.refs(d.get("from") or []), targets=texts.refs(d.get("to") or [])
        )
        yes = Act(a="dd", p=data.p, pg=data.pg, i=data.i, h=data.h, ok=True)
        await show(callback, bot, panel, (text, keyboards.confirm(yes, Nav(s="dc", p=data.p, pg=data.pg, i=data.i))))
        return

    def mutate(cfg: Any) -> None:
        if data.a == "dd":
            configstore.delete_direction(cfg, data.i, data.h)
        else:
            flag = "disable_edit" if data.a == "te" else "disable_delete"
            configstore.toggle_direction_flag(cfg, data.i, data.h, flag)

    after: Callable[[], Screen] = (
        (lambda: directions_screen(data.p, data.pg))
        if data.a == "dd"
        else (lambda: direction_screen(data.p, data.pg, data.i))
    )
    await _write(callback, callback_answer, bot, panel, store, data.p, mutate, after, back)


@router.callback_query(Act.filter(F.a.in_({"ge", "gd", "gm"})))
async def on_param_action(
    callback: CallbackQuery, callback_data: Act, callback_answer: CallbackAnswer,
    bot: Bot, panel: Panel, store: ConfigStore,
) -> None:
    key = {"ge": "disable_edit", "gd": "disable_delete", "gm": "mode"}[callback_data.a]
    pkey = callback_data.p
    await _write(
        callback, callback_answer, bot, panel, store, pkey,
        lambda cfg: configstore.toggle_global(cfg, key),
        lambda: params_screen(pkey),
        Nav(s="par", p=pkey),
    )


# ── add direction (FSM) ─────────────────────────────────────────────────────


def _add_text(project_key: str, body: str) -> str:
    return texts.ADD_HEADER.format(project=texts.PROJECT_TITLES[project_key]) + body


async def _edit_panel(message: Message, bot: Bot, panel: Panel, screen: Screen) -> None:
    # Keep the chat to one panel message: drop the typed input, edit the panel.
    with suppress(TelegramBadRequest):
        await message.delete()
    await panel.edit(bot, message.chat.id, screen[0], screen[1])


@router.callback_query(Act.filter(F.a == "add"))
async def on_add(
    callback: CallbackQuery, callback_data: Act, callback_answer: CallbackAnswer,
    bot: Bot, panel: Panel, state: FSMContext,
) -> None:
    project = status.project_by_key(callback_data.p)
    if project is None or not status.project_info(project).writable:
        callback_answer.text = texts.CONFIG_ERRORS["read_only"]
        callback_answer.show_alert = True
        return
    await state.set_state(AddDirection.source)
    await state.set_data({"p": project.key})
    await show(callback, bot, panel, (_add_text(project.key, texts.ADD_SOURCE), keyboards.add_cancel(project.key)))


@router.message(StateFilter(AddDirection.source), F.text)
async def on_add_source(message: Message, bot: Bot, panel: Panel, state: FSMContext) -> None:
    key = (await state.get_data()).get("p", "")
    try:
        source = configstore.normalize_chat_ref(message.text or "")
    except ConfigError as e:
        body = texts.config_error(e.code, e.detail) + "\n\n" + texts.ADD_SOURCE
        await _edit_panel(message, bot, panel, (_add_text(key, body), keyboards.add_cancel(key)))
        return
    await state.update_data(source=source)
    await state.set_state(AddDirection.targets)
    body = texts.ADD_TARGETS.format(source=texts.refs([source]))
    await _edit_panel(message, bot, panel, (_add_text(key, body), keyboards.add_cancel(key)))


@router.message(StateFilter(AddDirection.targets), F.text)
async def on_add_targets(message: Message, bot: Bot, panel: Panel, state: FSMContext) -> None:
    data = await state.get_data()
    key, source = data.get("p", ""), data.get("source", "")
    try:
        targets = configstore.parse_chat_refs(message.text or "")
    except ConfigError as e:
        body = texts.config_error(e.code, e.detail) + "\n\n" + texts.ADD_TARGETS.format(
            source=texts.refs([source])
        )
        await _edit_panel(message, bot, panel, (_add_text(key, body), keyboards.add_cancel(key)))
        return
    await state.update_data(targets=targets)
    await state.set_state(AddDirection.choice)
    body = texts.ADD_MODE.format(source=texts.refs([source]), targets=texts.refs(targets))
    await _edit_panel(message, bot, panel, (_add_text(key, body), keyboards.add_mode(key)))


def _summary(data: dict) -> Screen:
    key = data["p"]
    body = texts.ADD_SUMMARY.format(
        source=texts.refs([data["source"]]),
        targets=texts.refs(data["targets"]),
        mode=data["mode"],
        history=texts.HISTORY_FULL if data["history"] else texts.HISTORY_NONE,
    )
    return _add_text(key, body), keyboards.add_summary(key)


async def _add_data(state: FSMContext, *required: str) -> Optional[dict]:
    if await state.get_state() != AddDirection.choice.state:
        return None
    data = await state.get_data()
    return data if all(k in data for k in ("p", *required)) else None


async def _expired(callback: CallbackQuery, bot: Bot, panel: Panel, state: FSMContext, key: str) -> None:
    await state.clear()
    await show(callback, bot, panel, (texts.ADD_EXPIRED, keyboards.back(Nav(s="dl", p=key), texts.BTN_TO_LIST)))


@router.callback_query(Act.filter(F.a == "am"))
async def on_add_mode(
    callback: CallbackQuery, callback_data: Act, bot: Bot, panel: Panel, state: FSMContext
) -> None:
    data = await _add_data(state, "source", "targets")
    if data is None:
        await _expired(callback, bot, panel, state, callback_data.p)
        return
    mode = "forward" if callback_data.i == 1 else "copy"
    project = status.project_by_key(data["p"])
    if project is not None and not project.live:
        # The courses config is only ever replayed — a direction there without
        # past_mode would be ignored by past_mode.py.
        await state.update_data(mode=mode, history=True)
        await show(callback, bot, panel, _summary({**data, "mode": mode, "history": True}))
        return
    await state.update_data(mode=mode)
    body = texts.ADD_HISTORY.format(
        source=texts.refs([data["source"]]), targets=texts.refs(data["targets"]), mode=mode
    )
    await show(callback, bot, panel, (_add_text(data["p"], body), keyboards.add_history(data["p"])))


@router.callback_query(Act.filter(F.a == "ah"))
async def on_add_history(
    callback: CallbackQuery, callback_data: Act, bot: Bot, panel: Panel, state: FSMContext
) -> None:
    data = await _add_data(state, "source", "targets", "mode")
    if data is None:
        await _expired(callback, bot, panel, state, callback_data.p)
        return
    history = callback_data.i == 1
    await state.update_data(history=history)
    await show(callback, bot, panel, _summary({**data, "history": history}))


@router.callback_query(Act.filter(F.a == "as"))
async def on_add_save(
    callback: CallbackQuery, callback_data: Act, callback_answer: CallbackAnswer,
    bot: Bot, panel: Panel, state: FSMContext, store: ConfigStore,
) -> None:
    data = await _add_data(state, "source", "targets", "mode", "history")
    if data is None:
        await _expired(callback, bot, panel, state, callback_data.p)
        return
    await state.clear()
    key = data["p"]

    def mutate(cfg: Any) -> None:
        configstore.add_direction(cfg, [data["source"]], data["targets"], data["mode"], data["history"])

    await _write(
        callback, callback_answer, bot, panel, store, key, mutate,
        lambda: directions_screen(key, 10**6),  # clamps to the last page
        Nav(s="dl", p=key),
    )


@router.callback_query(Act.filter(F.a == "ax"))
async def on_add_cancel(
    callback: CallbackQuery, callback_data: Act, bot: Bot, panel: Panel, state: FSMContext
) -> None:
    await state.clear()
    await show(callback, bot, panel, directions_screen(callback_data.p, 0))
