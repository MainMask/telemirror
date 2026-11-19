"""The main menu and every screen's keyboard, built from ``registry``."""

from itertools import groupby
from typing import Optional, Sequence

from aiogram.types import InlineKeyboardMarkup, KeyboardButton, KeyboardButtonRequestChat, ReplyKeyboardMarkup

from bot.callbacks import ActCB, NavCB
from bot.keyboards.common import Row, button, markup
from bot.registry import BACK, DANGER, MAIN_MENU, PRIMARY, REFRESH, SCREENS, TITLES, children

SHORT = 16  # two labels this short fit side by side on a phone; a longer one gets its own row


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t) for t in MAIN_MENU]],
        resize_keyboard=True, input_field_placeholder="Выберите раздел",
    )


# request_chat's ids: what the picked chat was asked as
PICK_CHANNEL, PICK_GROUP = 1, 2


def chat_picker() -> ReplyKeyboardMarkup:
    """The main menu with 📺 Канал · 👥 Группа above it: Telegram's own list of the
    admin's chats, the pick sent back as ``chat_shared`` (middlewares.ChatPicked
    puts the main menu back)."""
    def pick(label: str, request_id: int, channel: bool) -> KeyboardButton:
        return KeyboardButton(text=TITLES[label], request_chat=KeyboardButtonRequestChat(
            request_id=request_id, chat_is_channel=channel, request_title=True))
    return ReplyKeyboardMarkup(
        keyboard=[[pick("pick_channel", PICK_CHANNEL, True), pick("pick_group", PICK_GROUP, False)],
                  [KeyboardButton(text=t) for t in MAIN_MENU]],
        resize_keyboard=True, input_field_placeholder="Выберите канал кнопкой ниже",
    )


def _pairs(buttons: list) -> list:
    """Two short labels in a row, a long one alone — and a red one (registry.DANGER)
    alone, so it isn't tapped for its neighbour."""
    rows, i = [], 0
    while i < len(buttons):
        pair = (i + 1 < len(buttons) and max(len(buttons[i].text), len(buttons[i + 1].text)) <= SHORT
                and DANGER not in (buttons[i].style, buttons[i + 1].style))
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
    primary: str = "",
) -> InlineKeyboardMarkup:
    """A screen's buttons (``titles``: labels showing a value, ``hidden``: ones
    that don't apply now, ``primary``: the one to tap now, in blue), a group's
    on rows of their own, its view's ``own`` rows, the screens opened from it
    (two per row), then 🔄 Обновить and ⬅️ Назад (to its parent, or ``back``)."""
    screen = SCREENS[screen_id]
    titles = titles or {}
    rows: list = []
    shown = [b for b in screen.buttons if b.action not in hidden]
    for _, group in groupby(shown, key=lambda b: b.group):
        rows += _pairs([
            button(titles.get(b.action, b.title), ActCB(a=b.action, p=project, i=i, pg=pg, h=h),
                   PRIMARY if b.action == primary else b.style)
            for b in group
        ])
    rows += [list(r) for r in own]
    # a child without a list of its own keeps the page, for its ⬅️ Назад
    opened = [button(f"{c.title} ›", NavCB(s=c.id, p=project, i=i, pg=0 if c.paged else pg))
              for c in children(screen_id)]
    rows += [opened[n:n + 2] for n in range(0, len(opened), 2)]
    last = []
    if screen.refresh:
        last.append(button(REFRESH, NavCB(s=screen_id, p=project, i=i, pg=pg)))
    if back is not None or screen.parent:
        last.append(button(BACK, back or NavCB(s=screen.parent, p=project, i=i, pg=pg)))
    return markup([*rows, last])
