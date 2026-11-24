"""The menu as data (bot/registry.py) keeps the bot uniform:
every button handled, one emoji = one meaning, Russian labels, a sound tree."""

import importlib
import re
from itertools import groupby

from bot import registry
from bot.keyboards.menu import SHORT, screen_kb
from bot.routers._common import CONFIRMED, HANDLED, INPUTS
from bot.screens import VIEWS

importlib.import_module("bot.app")  # registers every router's handlers

LABELS = [s.title for s in registry.SCREENS.values()] + [
    b.title for s in registry.SCREENS.values() for b in s.buttons
] + list(registry.TITLES.values())


def test_every_button_has_a_handler_and_every_handler_a_button():
    assert registry.unhandled_actions(HANDLED) == []
    assert registry.unknown_actions(HANDLED) == []


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
        assert re.fullmatch(r"[А-Яа-яЁё .,\-]+(\.jsession)?(N…| @…|…)?", words), label


def test_the_tree_is_sound():
    for screen in registry.SCREENS.values():
        if screen.parent:
            assert screen.parent in registry.SCREENS
            assert screen.project or not registry.SCREENS[screen.parent].project, screen.id
        assert registry.trail(screen.id)[0].parent == ""
    assert registry.MAIN_MENU == ("📁 Проекты", "📊 Статус", "⚙️ Настройки")


def test_screens_opened_from_a_list_have_a_view():
    for screen_id in registry._NOT_LISTED:
        assert screen_id in VIEWS, screen_id


def test_confirmations_and_inputs_are_registered():
    assert {"unit_start", "unit_stop", "unit_restart", "delete", "dir_del", "cfg_put", "cfg_undo", "task",
            "acc_del", "flt_del"} <= set(CONFIRMED)
    assert {"rename", "icon", "global", "dir_src", "dir_delay", "filter_items"} <= set(INPUTS)


def test_menu_path_names_the_way_there():
    assert registry.menu_path("dir_add") == "📁 Проекты → проект → 🔀 Направления → ➕ Добавить"
    assert registry.menu_path("p_link") == "📁 Проекты → проект → ⚙️ Настройки проекта → 🔗 Запасная ссылка"
    assert registry.menu_path("acc_login") == "⚙️ Настройки → 👤 Аккаунты → 🔑 Войти по номеру"
    assert registry.menu_path("ca") == "📁 Проекты → проект → 🛠 Инструменты → 🛂 Проверка доступа"
    assert registry.menu_path("cfg_get") == "📁 Проекты → проект → ⚙️ Настройки проекта → 💾 Файл настроек → 📥 Скачать"


def test_a_screens_groups_are_each_in_one_place():
    """A subheading once on its screen: its buttons together under it."""
    for screen in registry.SCREENS.values():
        groups = [g for g, _ in groupby(b.group for b in screen.buttons)]
        assert len(groups) == len(set(groups)), screen.id


def test_colours_follow_one_rule():
    """Red only for what can't be undone, green only for a confirmation; blue is
    picked by a view, one per screen (screen_kb's ``primary``)."""
    danger = {b.action for s in registry.SCREENS.values() for b in s.buttons if b.style}
    assert danger == {"delete", "dir_del", "acc_del", "cc_run"}
    for s in registry.SCREENS.values():
        for b in s.buttons:
            assert b.style in ("", registry.DANGER), b.action
    assert set(registry.LABEL_STYLES.values()) <= {registry.DANGER, registry.SUCCESS}
    for label, style in registry.LABEL_STYLES.items():
        assert (style == registry.DANGER) == label.startswith("🗑"), label


def test_screen_kb_colours_the_primary_and_the_dangerous():
    kb = screen_kb("card", "p", primary="restart")
    styles = {b.text: b.style for row in kb.inline_keyboard for b in row}
    assert styles["🔁 Перезапустить"] == registry.PRIMARY
    assert [s for s in styles.values() if s == registry.PRIMARY] == [registry.PRIMARY]
    assert {b.text: b.style for row in screen_kb("mng", "p").inline_keyboard for b in row}[
        "🗑 Удалить проект"] == registry.DANGER


def test_a_group_starts_its_own_row():
    rows = [[b.text for b in row] for row in screen_kb("mng", "p").inline_keyboard]
    copying = {b.title for b in registry.SCREENS["mng"].buttons if b.group == registry.COPYING}
    for row in rows:
        assert set(row) <= copying or not set(row) & copying, row


def test_two_buttons_share_a_row_only_when_both_are_short():
    """Paired, a long label is cut on a phone: the screens opened from a
    screen (›) are laid out as its own buttons."""
    for screen_id in registry.SCREENS:
        for row in screen_kb(screen_id, "p").inline_keyboard:
            if len(row) == 2:
                assert max(len(b.text) for b in row) <= SHORT, (screen_id, [b.text for b in row])
