"""CallbackData factories (aiogram packs them as ``prefix:field:…``, ≤64 bytes —
``pack()`` raises past that; tests cover the worst case)."""

from aiogram.filters.callback_data import CallbackData


class Nav(CallbackData, prefix="n"):
    """Open a screen.

    ``s`` — screen code; ``p`` — project/unit key; ``pg`` — page; ``i`` — index."""

    s: str
    p: str = ""
    pg: int = 0
    i: int = -1


class Act(CallbackData, prefix="a"):
    """Do something. ``ok=False`` shows the confirmation for destructive
    actions, ``ok=True`` performs it. ``h`` — direction fingerprint."""

    a: str
    p: str = ""
    pg: int = 0
    i: int = -1
    h: str = ""
    ok: bool = False
