"""How the panel shows a screen (after teleharvester's ``bot/services/screens.py``).

Every screen is opened the same way (``open_screen``): a main-menu button as a
new message, a screen's button (›, ⬅️ Назад, 🔄) in that message's place. A
project's screen gets its project loaded here — a deleted one shows
📁 Проекты instead, whichever way it was opened. A screen with live content
registers a view (``@view(id)``); the rest are shown as the registry has them.
Text is HTML; anything from outside goes through ``texts.esc``.
"""

from itertools import groupby
from typing import Awaitable, Callable, Optional, Sequence

from bot import status, texts
from bot.callbacks import NavCB
from bot.keyboards.common import Row
from bot.keyboards.menu import screen_kb
from bot.registry import CARD, SCREENS, children, trail
from bot.texts import esc, head
from telemirror.projects import Project

MAX_TEXT = 4096

View = Callable[..., Awaitable[None]]  # (message, edit, nav, *, project, note, **deps)
VIEWS: dict = {}


def view(screen_id: str):
    """Register the decorated coroutine as the screen's view."""
    def register(function: View) -> View:
        VIEWS[screen_id] = function
        return function
    return register


def title_line(screen_id: str, project: Optional[Project] = None, parent: str = "") -> str:
    """The screen's title; a project's as a path from its card —
    ``🏰 <b>Цитадель</b> › <b>🔀 Направления</b>`` (the project's icon for 📁).
    ``parent``: where the screen was opened from, when it isn't the registry's."""
    if project is None or not SCREENS[screen_id].project:
        return head(SCREENS[screen_id].title)
    crumbs = [*trail(parent), SCREENS[screen_id]] if parent else trail(screen_id)
    below = [s.title for s in crumbs if s.title != CARD and s.project]
    return " › ".join([f"{esc(project.icon)} {head(project.name)}", *(head(t) for t in below)])


def _line(label: str, hint: str) -> str:
    return f"{head(label)} — {esc(hint)}"


def fit(text: str) -> str:
    """Last-resort guard (screens are built to stay far below): whole lines only,
    a cut one could split an HTML tag."""
    if len(text) <= MAX_TEXT:
        return text
    return text[: MAX_TEXT - 2].rsplit("\n", 1)[0] + "\n…"


def screen_text(
    screen_id: str,
    project: Optional[Project] = None,
    *,
    body: str = "",
    note: str = "",
    more: str = "",
    hidden: Sequence[str] = (),
    titles: Optional[dict] = None,
    own_hints: Sequence[tuple] = (),
    parent: str = "",
) -> str:
    """``note`` (an action's result) on top, the title line, the view's ``body``,
    then — folded, its first lines showing — each button with what it does
    (under its group's subheading) and each screen opened from here, and
    ``more`` (how it works, details) folded at the end."""
    titles = titles or {}
    screen = SCREENS[screen_id]
    blocks = [note, title_line(screen_id, project, parent), body]
    hints = []
    shown = [b for b in screen.buttons if b.action not in hidden]
    for group, buttons in groupby(shown, key=lambda b: b.group):
        lines = [_line(titles.get(b.action, b.title), b.hint) for b in buttons]
        hints.append("\n".join([f"<i>{esc(group)}</i>", *lines] if group else lines))
    hints.append("\n".join([_line(label, hint) for label, hint in own_hints]
                           + [_line(titles.get(c.id, c.title), c.hint)
                              for c in children(screen_id) if c.id not in hidden]))
    if folded := "\n\n".join(h for h in hints if h):
        blocks.append(texts.more(folded))
    if more:
        blocks.append(texts.more(more))
    return fit("\n\n".join(b for b in blocks if b))


def send(message, edit: bool):
    """In the message's place (a button's), else as a new message."""
    return message.edit_text if edit else message.answer


async def show(
    message,
    edit: bool,
    screen_id: str,
    project: Optional[Project] = None,
    *,
    body: str = "",
    note: str = "",
    more: str = "",
    hidden: Sequence[str] = (),
    titles: Optional[dict] = None,
    own: Sequence[Row] = (),
    own_hints: Sequence[tuple] = (),
    i: int = -1,
    pg: int = 0,
    h: str = "",
    back: Optional[NavCB] = None,
    parent: str = "",
    primary: str = "",
):
    key = project.key if project else ""
    text = screen_text(screen_id, project, body=body, note=note, more=more, hidden=hidden, titles=titles,
                       own_hints=own_hints, parent=parent)
    kb = screen_kb(screen_id, key, i=i, pg=pg, h=h, hidden=hidden, titles=titles, own=own, back=back,
                   primary=primary)
    return await send(message, edit)(text, reply_markup=kb)


async def open_screen(nav: NavCB, message, edit: bool, deps: dict, note: str = ""):
    """The screen by its view, or as the registry has it. ``deps``: the
    services views take by name (``middlewares.Services``)."""
    project = None
    if SCREENS[nav.s].project:
        project = status.find(nav.p)
        if project is None:
            nav, note = NavCB(s="prj"), texts.NO_PROJECT
    if nav.s in VIEWS:
        await VIEWS[nav.s](message, edit, nav, project=project, note=note, **deps)
    else:
        await show(message, edit, nav.s, project, note=note, i=nav.i, pg=nav.pg)
