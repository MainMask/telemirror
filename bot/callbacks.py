"""CallbackData factories (aiogram packs them as ``prefix:field:…``, ≤64 bytes —
``pack()`` raises past that; tests cover the worst case).

Buttons carry short ids and indexes, never names: a project by its key, a
direction by its index plus a fingerprint (``h``), so a tap can't land on
another one after the list changed."""

from aiogram.filters.callback_data import CallbackData


class NavCB(CallbackData, prefix="n"):
    """Open a screen (``registry.SCREENS`` id ``s``) of project ``p``; ``i`` — the
    item it shows (a direction, a filter…), ``pg`` — the page of its list."""

    s: str
    p: str = ""
    i: int = -1
    pg: int = 0


class ActCB(CallbackData, prefix="a"):
    """A screen's button (``registry.Button.action`` ``a``) or a view's own one."""

    a: str
    p: str = ""
    i: int = -1
    pg: int = 0
    h: str = ""


class FltCB(CallbackData, prefix="f"):
    """Filter editor. ``a``: ``v`` view / ``x`` delete item / ``+`` add items /
    ``t`` toggle a bool / ``e`` type a scalar / ``u``, ``w`` move up, down /
    ``r`` delete the filter / ``n`` add a filter (``h`` = the direction's
    fingerprint then). ``d`` — direction index (-1 = the project's filters),
    ``f`` — filter index, ``k`` — arg index (``configedit.filter_args``),
    ``n`` — item index, ``pg`` — items page, ``h`` — fingerprint of the filter entry."""

    a: str
    p: str
    d: int = -1
    f: int = 0
    k: int = 0
    n: int = -1
    pg: int = 0
    h: str = ""


class ChoiceCB(CallbackData, prefix="c"):
    """A form's button: the only kind that keeps the chat in its form (any other
    tap leaves it — ``middlewares.LeaveFormOnNavigation``). ``scope`` names the
    step, ``value`` the choice (an index, a token…)."""

    scope: str
    value: str = ""
