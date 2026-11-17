"""The menu as data (telemirror/panel/registry.py) keeps the bot uniform:
every button handled, one emoji = one meaning, Russian labels, a sound tree."""

import importlib
import re

from telemirror.panel import registry
from telemirror.panel.routers._common import CONFIRMED, HANDLED, INPUTS
from telemirror.panel.screens import VIEWS

importlib.import_module("telemirror.panel.app")  # registers every router's handlers

LABELS = [s.title for s in registry.SCREENS.values()] + [
    b.title for s in registry.SCREENS.values() for b in s.buttons
]


def test_every_button_has_a_handler():
    assert registry.unhandled_actions(HANDLED) == []


def _root(label: str) -> str:
    words = [w for w in re.findall(r"[А-Яа-яЁё]+", label) if w.lower() != "да"]
    return words[0].lower()[:5]


def test_one_emoji_one_meaning():
    """Labels sharing an emoji share their first word's root (📁 Проекты /
    📁 Проект, 🗑 Удалить / 🗑 Да, удалить) — except the shared verbs."""
    shared = {registry.emoji_of(e) for e in registry.SHARED_EMOJI}
    roots: dict = {}
    for label in LABELS:
        roots.setdefault(registry.emoji_of(label), {}).setdefault(_root(label), label)
    clashes = {e: sorted(r.values()) for e, r in roots.items() if len(r) > 1 and e not in shared}
    assert clashes == {}


def test_the_confirm_and_cancel_labels_follow_the_rule():
    assert _root(registry.YES_DELETE) == _root("🗑 Удалить")


def test_labels_are_an_emoji_and_russian_words():
    for label in LABELS:
        emoji, _, words = label.partition(" ")
        assert emoji and not re.search(r"[\w]", emoji), label
        assert re.fullmatch(r"[А-Яа-яЁё .,\-]+(\.jsession)?", words), label


def test_the_tree_is_sound():
    for screen in registry.SCREENS.values():
        if screen.parent:
            assert screen.parent in registry.SCREENS
            assert screen.project or not registry.SCREENS[screen.parent].project, screen.id
        assert registry.trail(screen.id)[0].parent == ""
    assert registry.MAIN_MENU == ("📁 Проекты", "📊 Задачи", "⚙️ Настройки")


def test_screens_opened_from_a_list_have_a_view():
    for screen_id in registry._NOT_LISTED:
        assert screen_id in VIEWS or screen_id == "fv", screen_id  # fv: opened by the filter editor


def test_confirmations_and_inputs_are_registered():
    assert {"start", "stop", "restart", "delete", "dir_del", "cfg_put", "cfg_undo", "task", "acc_del"} <= set(CONFIRMED)
    assert {"rename", "icon", "global", "dir_src", "dir_delay", "filter_items"} <= set(INPUTS)


def test_menu_path_names_the_way_there():
    assert registry.menu_path("dir_add") == "📁 Проекты → проект → 🔀 Направления → ➕ Добавить"
    assert registry.menu_path("acc") == "⚙️ Настройки → 👤 Аккаунты"
