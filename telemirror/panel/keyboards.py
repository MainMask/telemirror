"""Keyboard builders — markup only, no I/O and no decisions beyond layout."""

from typing import Iterable, Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from telemirror.panel import settings, texts
from telemirror.panel.callbacks import Act, Nav


def main_reply() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.button(text=texts.BTN_PROJECTS)
    kb.button(text=texts.BTN_TASKS)
    kb.button(text=texts.BTN_SETTINGS)
    kb.adjust(3)
    return kb.as_markup(
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder=texts.REPLY_PLACEHOLDER,
    )


def _btn(text: str, cb: "Nav | Act") -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=cb.pack())


def _rows(rows: Iterable[Iterable[Optional[InlineKeyboardButton]]]) -> InlineKeyboardMarkup:
    """Rows of buttons; ``None`` entries and empty rows are dropped."""
    out = [[b for b in row if b is not None] for row in rows]
    return InlineKeyboardMarkup(inline_keyboard=[r for r in out if r])


def confirm(yes: Act, no: "Nav | Act") -> InlineKeyboardMarkup:
    return _rows([[_btn(texts.BTN_YES, yes), _btn(texts.BTN_NO, no)]])


def back(cb: Nav, text: str = texts.BTN_BACK) -> InlineKeyboardMarkup:
    return _rows([[_btn(text, cb)]])


# ── tasks ───────────────────────────────────────────────────────────────────


def tasks_list(items: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    """items: (unit key, label)."""
    rows = [[_btn(label, Nav(s="uc", p=key))] for key, label in items]
    rows.append([_btn(texts.BTN_REFRESH, Nav(s="tsk"))])
    return _rows(rows)


def unit_card(key: str, running: bool, available: bool) -> InlineKeyboardMarkup:
    controls: list[Optional[InlineKeyboardButton]] = []
    if available:
        if key == "live":
            if running:
                controls = [
                    _btn(texts.BTN_RESTART, Act(a="rst", p=key)),
                    _btn(texts.BTN_STOP, Act(a="stop", p=key)),
                ]
            else:
                controls = [_btn(texts.BTN_START, Act(a="start", p=key))]
        elif running:
            controls = [_btn(texts.BTN_STOP, Act(a="stop", p=key))]
        elif key == "crs":
            controls = [_btn(texts.BTN_START_REPLAY, Act(a="start", p=key))]
    return _rows([
        controls,
        [_btn(texts.BTN_REFRESH, Nav(s="uc", p=key)), _btn(texts.BTN_TO_TASKS, Nav(s="tsk"))],
    ])


def cancel_pick(keys: list[str]) -> InlineKeyboardMarkup:
    rows = [[_btn(f"{texts.BTN_STOP}: {texts.UNIT_TITLES[k]}", Act(a="stop", p=k))] for k in keys]
    return _rows(rows)


# ── projects ────────────────────────────────────────────────────────────────


def projects_list(items: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    return _rows([[_btn(label, Nav(s="pc", p=key))] for key, label in items])


def project_card(
    key: str, live: bool, readable: bool, unit_running: bool, available: bool
) -> InlineKeyboardMarkup:
    action: Optional[InlineKeyboardButton] = None
    if available:
        if live:
            action = _btn(texts.BTN_APPLY, Act(a="rst", p="live", h="pc"))
        elif unit_running:
            action = _btn(texts.BTN_STOP_REPLAY, Act(a="stop", p=key, h="pc"))
        else:
            action = _btn(texts.BTN_START_REPLAY, Act(a="start", p=key, h="pc"))
    sections = (
        [
            _btn(texts.BTN_DIRECTIONS, Nav(s="dl", p=key)),
            _btn(texts.BTN_FILTERS, Nav(s="flt", p=key)),
            _btn(texts.BTN_PARAMS, Nav(s="par", p=key)),
        ]
        if readable
        else []
    )
    return _rows([
        sections[:2],
        sections[2:],
        [action],
        [_btn(texts.BTN_TO_PROJECTS, Nav(s="prj"))],
    ])


def directions_list(
    key: str, page: int, pages: int, items: list[tuple[int, str]], writable: bool
) -> InlineKeyboardMarkup:
    rows: list[list[Optional[InlineKeyboardButton]]] = [
        [_btn(label, Nav(s="dc", p=key, pg=page, i=idx))] for idx, label in items
    ]
    if pages > 1:
        rows.append([
            _btn(texts.BTN_PREV, Nav(s="dl", p=key, pg=page - 1)) if page > 0 else None,
            _btn(f"{page + 1}/{pages}", Nav(s="dl", p=key, pg=page)),
            _btn(texts.BTN_NEXT, Nav(s="dl", p=key, pg=page + 1)) if page < pages - 1 else None,
        ])
    rows.append([_btn(texts.BTN_ADD, Act(a="add", p=key)) if writable else None])
    rows.append([_btn(texts.BTN_TO_PROJECT, Nav(s="pc", p=key))])
    return _rows(rows)


def direction_card(
    key: str, page: int, idx: int, fp: str, edit_on: bool, delete_on: bool, writable: bool
) -> InlineKeyboardMarkup:
    rows: list[list[Optional[InlineKeyboardButton]]] = []
    if writable:
        rows.append([
            _btn(texts.BTN_TOGGLE_EDIT.format(state=texts.on_off(edit_on)),
                 Act(a="te", p=key, pg=page, i=idx, h=fp)),
            _btn(texts.BTN_TOGGLE_DELETE.format(state=texts.on_off(delete_on)),
                 Act(a="td", p=key, pg=page, i=idx, h=fp)),
        ])
        rows.append([_btn(texts.BTN_DELETE, Act(a="dd", p=key, pg=page, i=idx, h=fp))])
    rows.append([_btn(texts.BTN_TO_LIST, Nav(s="dl", p=key, pg=page))])
    return _rows(rows)


def add_mode(key: str) -> InlineKeyboardMarkup:
    return _rows([
        [_btn(texts.BTN_MODE_COPY, Act(a="am", p=key, i=0)),
         _btn(texts.BTN_MODE_FORWARD, Act(a="am", p=key, i=1))],
        [_btn(texts.BTN_CANCEL, Act(a="ax", p=key))],
    ])


def add_history(key: str) -> InlineKeyboardMarkup:
    return _rows([
        [_btn(texts.BTN_HISTORY_NONE, Act(a="ah", p=key, i=0)),
         _btn(texts.BTN_HISTORY_FULL, Act(a="ah", p=key, i=1))],
        [_btn(texts.BTN_CANCEL, Act(a="ax", p=key))],
    ])


def add_summary(key: str) -> InlineKeyboardMarkup:
    return _rows([[_btn(texts.BTN_SAVE, Act(a="as", p=key)), _btn(texts.BTN_CANCEL, Act(a="ax", p=key))]])


def add_cancel(key: str) -> InlineKeyboardMarkup:
    return _rows([[_btn(texts.BTN_CANCEL, Act(a="ax", p=key))]])


def params(key: str, edit_on: bool, delete_on: bool, mode: str, writable: bool) -> InlineKeyboardMarkup:
    rows: list[list[Optional[InlineKeyboardButton]]] = []
    if writable:
        rows.append([
            _btn(texts.BTN_PARAM_EDIT.format(state=texts.on_off(edit_on)), Act(a="ge", p=key)),
            _btn(texts.BTN_PARAM_DELETE.format(state=texts.on_off(delete_on)), Act(a="gd", p=key)),
        ])
        rows.append([_btn(texts.BTN_PARAM_MODE.format(mode=mode), Act(a="gm", p=key))])
    rows.append([_btn(texts.BTN_TO_PROJECT, Nav(s="pc", p=key))])
    return _rows(rows)


# ── settings / maintenance ──────────────────────────────────────────────────


def settings_screen() -> InlineKeyboardMarkup:
    return _rows([
        [_btn(texts.BTN_MAINTENANCE, Nav(s="mnt"))],
        [_btn(texts.BTN_REFRESH, Nav(s="set"))],
    ])


def maintenance() -> InlineKeyboardMarkup:
    return _rows([
        [_btn(texts.BTN_RS, Nav(s="rs")), _btn(texts.BTN_SP, Nav(s="sp"))],
        [_btn(texts.BTN_TO_SETTINGS, Nav(s="set"))],
    ])


def task_screen(key: str, can_real: bool, flags: Optional[set[str]] = None) -> InlineKeyboardMarkup:
    rows: list[list[Optional[InlineKeyboardButton]]] = []
    if flags is not None:
        for i, flag in enumerate(settings.SYNC_PINS_FLAGS):
            mark = "☑️" if flag in flags else "⬜️"
            rows.append([_btn(f"{mark} {texts.SP_FLAGS[flag]}", Act(a="spf", p=key, i=i))])
    real = texts.BTN_RUN_SP if key == "sp" else texts.BTN_RUN_RS
    rows.append([
        _btn(texts.BTN_DRY_RUN, Act(a="run", p=key, i=0)),
        _btn(real, Act(a="run", p=key, i=1)) if can_real else None,
    ])
    rows.append([_btn(texts.BTN_OUTPUT, Nav(s="uc", p=key))])
    rows.append([_btn(texts.BTN_TO_MAINTENANCE, Nav(s="mnt")), _btn(texts.BTN_REFRESH, Nav(s=key))])
    return _rows(rows)
