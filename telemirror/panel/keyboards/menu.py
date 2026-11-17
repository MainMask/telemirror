"""The main menu and every screen's keyboard, built from ``registry``."""

from typing import Optional, Sequence

from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from telemirror.panel.callbacks import ActCB, NavCB
from telemirror.panel.keyboards.common import Row, button, markup
from telemirror.panel.registry import BACK, MAIN_MENU, REFRESH, SCREENS, children

SHORT = 16  # two labels this short fit side by side on a phone; a longer one gets its own row


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t) for t in MAIN_MENU]],
        resize_keyboard=True, input_field_placeholder="Выберите раздел",
    )


def _pairs(buttons: list) -> list:
    """Two short labels in a row, a long one alone."""
    rows, i = [], 0
    while i < len(buttons):
        pair = i + 1 < len(buttons) and max(len(buttons[i].text), len(buttons[i + 1].text)) <= SHORT
        rows.append(buttons[i:i + 2] if pair else [buttons[i]])
        i += 2 if pair else 1
    return rows


def screen_kb(
    screen_id: str,
    project: str = "",
    *,
    i: int = -1,
    pg: int = 0,
    h: str = "",
    hidden: Sequence[str] = (),
    titles: Optional[dict] = None,
    own: Sequence[Row] = (),
    back: Optional[NavCB] = None,
) -> InlineKeyboardMarkup:
    """A screen's buttons (``titles``: labels showing a value, ``hidden``: ones
    that don't apply now), its view's ``own`` rows, the screens opened from it
    (two per row), then 🔄 Обновить and ⬅️ Назад (to its parent, or ``back``)."""
    screen = SCREENS[screen_id]
    titles = titles or {}
    actions = [
        button(titles.get(b.action, b.title), ActCB(a=b.action, p=project, i=i, pg=pg, h=h))
        for b in screen.buttons if b.action not in hidden
    ]
    rows = _pairs(actions) + [list(r) for r in own]
    opened = [button(f"{c.title} ›", NavCB(s=c.id, p=project, i=i)) for c in children(screen_id)]
    rows += [opened[n:n + 2] for n in range(0, len(opened), 2)]
    last = []
    if screen.refresh:
        last.append(button(REFRESH, NavCB(s=screen_id, p=project, i=i, pg=pg)))
    if back is not None or screen.parent:
        last.append(button(BACK, back or NavCB(s=screen.parent, p=project, i=i, pg=pg)))
    return markup([*rows, last])
