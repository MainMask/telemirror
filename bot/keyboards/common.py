"""Small keyboard builders shared by every screen and form."""

from typing import Callable, Optional, Sequence

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.callbacks import ChoiceCB, NavCB
from bot.registry import BACK, CANCEL, LABEL_STYLES, NEXT, PREV, TITLES, YES

Row = list  # of InlineKeyboardButton


def button(text: str, cb: CallbackData, style: str = "") -> InlineKeyboardButton:
    """``style``: its colour (registry.PRIMARY…); a label of ``LABEL_STYLES``
    has its own wherever it is."""
    return InlineKeyboardButton(text=text, callback_data=cb.pack(), style=style or LABEL_STYLES.get(text))


def markup(rows: Sequence[Row]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[list(r) for r in rows if r])


def choice_kb(scope: str, options: Sequence[tuple], widths: Sequence[int] = (1,)) -> InlineKeyboardMarkup:
    """(label, value) choices of one form step; ``widths``: buttons per row
    (the last one repeats)."""
    builder = InlineKeyboardBuilder()
    for label, value in options:
        builder.button(text=label, callback_data=ChoiceCB(scope=scope, value=value), style=LABEL_STYLES.get(label))
    builder.adjust(*widths)
    return builder.as_markup()


def cancel_kb(step: str, kb: Optional[InlineKeyboardMarkup] = None) -> InlineKeyboardMarkup:
    """✖️ Отмена under a step's prompt (the step's state name; callback data
    can't hold ':', so it carries '.'); the step's own buttons above it."""
    cancel = [button(CANCEL, ChoiceCB(scope="cancel", value=step.replace(":", ".")))]
    return markup([*(kb.inline_keyboard if kb else []), cancel])


def confirm_kb(token: str, yes: str = YES) -> InlineKeyboardMarkup:
    """The confirmation of an action: ``yes`` (``✅ Да`` / ``🗑 Да, удалить``) and
    ✖️ Отмена side by side; the token makes only the latest one valid."""
    return markup([[button(yes, ChoiceCB(scope="yes", value=token)),
                    button(CANCEL, ChoiceCB(scope="no", value=token))]])


def pick_kb(kb: Optional[InlineKeyboardMarkup] = None) -> InlineKeyboardMarkup:
    """📇 Выбрать из списка under a prompt that takes a channel (``kb``: its own
    buttons, above it)."""
    return markup([*(kb.inline_keyboard if kb else []), [button(TITLES["pick"], ChoiceCB(scope="pick"))]])


def back_kb(nav: NavCB, label: str = BACK) -> InlineKeyboardMarkup:
    """One ⬅️ button: the end of a flow or a refusal is never a dead end."""
    return markup([[button(label, nav)]])


def pages(total: int, size: int) -> int:
    return max(1, -(-total // size))


def paged_rows(items: Sequence[InlineKeyboardButton], page: int, size: int,
               page_cb: Callable[[int], CallbackData]) -> list:
    """One item per row, a page of them; with more than a page ◀️ · 📄 N/M · ▶️
    under it (wrapping round; 📄 redraws the page shown)."""
    count = pages(len(items), size)
    page %= count
    rows = [[item] for item in items[page * size:(page + 1) * size]]
    if count > 1:
        rows.append([
            button(PREV, page_cb((page - 1) % count)),
            button(f"📄 {page + 1}/{count}", page_cb(page)),
            button(NEXT, page_cb((page + 1) % count)),
        ])
    return rows
