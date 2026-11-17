"""How the panel shows a screen (after teleharvester's ``bot/services/screens.py``).

Every screen is opened the same way (``open_screen``): a main-menu button as a
new message, a screen's button (›, ⬅️ Назад, 🔄) in that message's place. A
screen with live content registers a view (``@view(id)``); the rest are shown
as the registry has them. Text is HTML; anything from outside goes through
``esc``.
"""

from html import escape
from typing import Awaitable, Callable, Optional, Sequence

from telemirror.panel.callbacks import NavCB
from telemirror.panel.keyboards.common import Row
from telemirror.panel.keyboards.menu import screen_kb
from telemirror.panel.registry import CARD, SCREENS, children, trail
from telemirror.projects import Project, ProjectError, load_project

MAX_TEXT = 4096
NO_PROJECT = "⛔ Проект не найден — возможно, его удалили. Откройте 📁 Проекты заново."

View = Callable[..., Awaitable[None]]  # (message, edit, nav, state, **deps)
VIEWS: dict = {}


def view(screen_id: str):
    """Register the decorated coroutine as the screen's view."""
    def register(function: View) -> View:
        VIEWS[screen_id] = function
        return function
    return register


def find_project(key: str) -> Optional[Project]:
    try:
        return load_project(key)
    except ProjectError:
        return None


def esc(value: object) -> str:
    return escape(str(value), quote=False)


def head(label: str) -> str:
    return f"<b>{esc(label)}</b>"


def project_label(project: Project) -> str:
    return f"{project.icon} {project.name}"


def title_line(screen_id: str, project: Optional[Project] = None) -> str:
    """The screen's title; a project's as a path from its card —
    ``🏰 <b>Цитадель</b> › <b>🔀 Направления</b>`` (the project's icon for 📁)."""
    if project is None or not SCREENS[screen_id].project:
        return head(SCREENS[screen_id].title)
    below = [s.title for s in trail(screen_id) if s.title != CARD and s.project]
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
    hidden: Sequence[str] = (),
    titles: Optional[dict] = None,
    own_hints: Sequence[tuple] = (),
) -> str:
    """``note`` (an action's result) on top, the title line, the view's ``body``,
    then each button with what it does and each screen opened from here."""
    titles = titles or {}
    screen = SCREENS[screen_id]
    lines = [_line(titles.get(b.action, b.title), b.hint) for b in screen.buttons if b.action not in hidden]
    lines += [_line(label, hint) for label, hint in own_hints]
    lines += [_line(c.title, c.hint) for c in children(screen_id)]
    blocks = [note, title_line(screen_id, project), body, "\n".join(lines)]
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
    hidden: Sequence[str] = (),
    titles: Optional[dict] = None,
    own: Sequence[Row] = (),
    own_hints: Sequence[tuple] = (),
    i: int = -1,
    pg: int = 0,
    h: str = "",
    back: Optional[NavCB] = None,
):
    key = project.key if project else ""
    text = screen_text(screen_id, project, body=body, note=note, hidden=hidden, titles=titles, own_hints=own_hints)
    kb = screen_kb(screen_id, key, i=i, pg=pg, h=h, hidden=hidden, titles=titles, own=own, back=back)
    return await send(message, edit)(text, reply_markup=kb)


async def open_screen(nav: NavCB, message, edit: bool, state, deps: dict, note: str = ""):
    """The screen by its view, or as the registry has it (a project's: its project's)."""
    if nav.s in VIEWS:
        await VIEWS[nav.s](message, edit, nav, state, note=note, **deps)
        return
    project = None
    if SCREENS[nav.s].project:
        project = find_project(nav.p)
        if project is None:
            await send(message, edit)(NO_PROJECT)
            return
    await show(message, edit, nav.s, project, note=note, i=nav.i, pg=nav.pg)
