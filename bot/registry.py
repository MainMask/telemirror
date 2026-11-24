"""The whole menu of the control panel, as data (after teleharvester's
``modules/registry.py``): screens, their buttons and what each does. The
keyboards, the screens' texts and the menu paths in messages are built from
here, so a button can't lose its description or its handler — the bot refuses
to start with a button nobody handles (``unhandled_actions``).

A screen's message lists (folded) each of its buttons with its hint, under their
subheadings (``Button.group``); its keyboard has them two short ones per row,
a group's never mixed with another's, then the screens opened from it (``›``),
then ``🔄 Обновить`` and ``⬅️ Назад`` on the last row. ``⬅️ Назад`` returns to the
page of the list the screen was opened from. Views (``screens.view``) add
the live content and their own rows (a list, values on buttons).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Button:
    action: str  # ActCB.a — the handler is registered for it (routers)
    title: str  # emoji + one or two words
    hint: str  # what it does: one line next to it in the screen's message
    group: str = ""  # a subheading on its screen: its buttons together, under it (screens.screen_text)
    style: str = ""  # DANGER for what can't be undone (its colour, Bot API 9.4)


@dataclass(frozen=True)
class Screen:
    id: str  # NavCB.s
    title: str
    hint: str  # next to its button on the parent screen / in the /start message
    parent: str = ""  # its ⬅️ Назад; "" = a main-menu screen (reply keyboard)
    buttons: tuple = ()
    refresh: bool = False  # live state: 🔄 Обновить next to ⬅️ Назад
    project: bool = False  # one project's screen: its buttons carry the project key
    paged: bool = False  # has its own paged list (NavCB.pg is its page, not its parent's)


# Button colours (Bot API 9.4), one rule for the whole bot: at most one PRIMARY
# on a screen — the step to take now, picked by its view (screens.show's
# ``primary``); DANGER — what can't be undone; SUCCESS — a confirmation.
PRIMARY, DANGER, SUCCESS = "primary", "danger", "success"

# ── titles (button labels quote these, so a rename can't leave a stale one) ──
PROJECTS = "📁 Проекты"
TASKS = "📊 Статус"
SETTINGS = "⚙️ Настройки"
CARD = "📁 Проект"
DIRECTIONS = "🔀 Направления"
DIRECTION = "🔀 Направление"
BROADCAST = "📢 Рассылка"
FILTERS = "🧹 Фильтры"
DIR_FILTERS = "🧹 Фильтры направления"
FILTER = "🧹 Фильтр"
REPLAY = "⏪ Старые посты"
MAINTENANCE = "🛠 Инструменты"
RESTRICT = "🔒 Запрет копирования"
PINS = "📌 Закрепы"
ANONYMITY = "🕶 Анонимность"
ACCESS = "🛂 Проверка доступа"
CLEAR = "🧨 Очистка каналов"
CONFIG = "💾 Файл настроек"
FAILED = "❗ Не скопировано"  # telemirror.notify.FAILED_SCREEN
MANAGE = "⚙️ Настройки проекта"
UNIT = "📊 Статус и журнал"
ACCOUNTS = "👤 Аккаунты"
ACCOUNT = "👤 Аккаунт"
SELFCHECK = "🧾 Диагностика сервера"

BACK = "⬅️ Назад"
REFRESH = "🔄 Обновить"
CANCEL = "✖️ Отмена"
YES = "✅ Да"
YES_DELETE = "🗑 Да, удалить"
PREV, NEXT = "◀️", "▶️"

CHECK, RUN, STOP, LOG = "🔍 Проверить", "▶️ Выполнить", "⏹ Остановить", "📄 Журнал"
STOP_HINT = "прервать то, что выполняется"
CHECK_HINT = "пробный запуск: ничего не меняет, только показывает, что будет сделано"
RUN_HINT = "сделать то, что показала проверка"
LOG_HINT = "что происходило при последнем запуске"

# the subheadings of the screens' buttons
COPYING, PROJECT, RUN_SETTINGS, START, WHAT, WATCH = (
    "Копирование", "Проект", "Настройки запуска", "Запуск", "Что и как", "Присмотр за зеркалами")


def _tool(task: str, *flags: Button, check: str = CHECK_HINT, run: str = RUN_HINT, danger: bool = False) -> tuple:
    """A tool's buttons, the same on every tool's screen: 🔍 Проверить, ▶️ Выполнить,
    ⏹ Остановить, 📄 Журнал, then its run's settings."""
    return (
        Button(f"{task}_dry", CHECK, check),
        Button(f"{task}_run", RUN, run, style=DANGER if danger else ""),
        Button(f"{task}_stop", STOP, STOP_HINT),
        Button(f"{task}_log", LOG, LOG_HINT),
        *flags,
    )


SCREENS = {s.id: s for s in (
    Screen("prj", PROJECTS, "ваши зеркала: откуда, куда и от чьего имени копировать", buttons=(
        Button("new", "➕ Новый проект", "имя, значок и аккаунт — потом каналы"),
    ), refresh=True, paged=True),
    # a project's card and its screens, in the order of the work
    Screen("card", CARD, "направления, фильтры, история, инструменты, настройки", "prj", buttons=(
        Button("start", "▶️ Запустить", "начать копировать новые посты"),
        Button("stop", "⏹ Остановить", "перестать копировать новые посты"),
        Button("restart", "🔁 Перезапустить", "применить сделанные изменения"),
    ), refresh=True, project=True),
    Screen("dirs", DIRECTIONS, "из каких каналов в какие копировать", "card", buttons=(
        Button("dir_add", "➕ Добавить", "новое направление: источник → куда копировать"),
        Button("dir_find", "🔎 Найти", "по названию канала или его ID"),
    ), project=True, paged=True),
    Screen("dir", DIRECTION, "одно направление: откуда и куда", "dirs", buttons=(
        Button("dir_src", "📨 Откуда", "каналы, из которых берутся посты"),
        Button("dir_dst", "🎯 Куда", "каналы, в которые посты копируются"),
        Button("dir_delay", "⏱ Пауза между отправками", "сколько секунд ждать между отправками"),
        Button("dir_del", "🗑 Удалить направление", "убрать это направление", style=DANGER),
    ), project=True),
    Screen("dflt", DIR_FILTERS, "свой список фильтров вместо общих", "dir", project=True),
    Screen("bc", BROADCAST, "канал, посты которого копируются во все ваши каналы", "dirs", buttons=(
        Button("p_bc", "📢 Рассылать из канала", "какой канал рассылать"),
        Button("p_bct", "📬 Куда рассылать", "если не во все ваши каналы"),
    ), project=True),
    Screen("flt", FILTERS, "что не копировать и что менять в постах", "card", project=True),
    Screen("fv", FILTER, "настройки одного фильтра", "flt", project=True),
    Screen("rpl", REPLAY, "скопировать посты, вышедшие до запуска зеркала", "card", buttons=(
        Button("rpl_start", "▶️ Начать копирование", "новые посты на это время подождут", START),
        Button("rpl_stop", "⏸ Приостановить", "в следующий раз продолжит с того же места", START),
        Button("rpl_restart", "🔁 Перезапустить зеркало", "чтобы новый темп начал действовать", START),
        Button("rpl_hist", "📜 Что копировать", "все старые посты, последние N, с даты или ничего", WHAT),
        Button("rpl_delay", "⏱ Пауза для старых постов", "сколько секунд ждать между старыми постами", WHAT),
        Button("rpl_pace", "🐢 Темп", "сразу или порциями: N постов за M минут, зеркало не останавливается", WHAT),
    ), refresh=True, project=True),
    Screen("mnt", MAINTENANCE, "разовые действия с вашими каналами: проверить доступ, перенести закрепы, очистить", "card",
           project=True),
    Screen("ca", ACCESS, "видит ли аккаунт источники и может ли публиковать в ваших каналах", "mnt", buttons=(
        Button("ca_dry", CHECK, "ничего не меняет: только проверяет права аккаунта"),
        Button("ca_stop", STOP, STOP_HINT),
        Button("ca_log", LOG, LOG_HINT),
    ), refresh=True, project=True),
    Screen("rs", RESTRICT, "запретить сохранять и пересылать посты ваших каналов", "mnt",
           buttons=_tool("rs"), refresh=True, project=True),
    Screen("sp", PINS, "закрепить у вас то же, что закреплено в источниках", "mnt", buttons=_tool(
        "sp",
        # flags of the run (☑️ / ⬜ on the button): settings.SYNC_PINS_FLAGS, in this order
        Button("sp_additive", "☑️ Только добавлять", "не откреплять то, что открепили в источнике", RUN_SETTINGS),
        Button("sp_allow_clear", "☑️ Снимать все", "откреплять всё, если в источнике закрепов нет", RUN_SETTINGS),
        Button("sp_broadcast", "☑️ С рассылкой", "и канал рассылки", RUN_SETTINGS),
        Button("sp_thorough", "☑️ Тщательно", "каждую тему группы — дольше", RUN_SETTINGS),
        Button("sp_max", "📏 Лимит закрепов", "сколько закрепов смотреть в чате или теме", RUN_SETTINGS),
        Button("sp_only", "📍 Выбрать источники", "только эти источники вместо всех", RUN_SETTINGS),
        run="сделать то, что показала проверка с теми же настройками",
    ), refresh=True, project=True),
    Screen("ag", ANONYMITY, "скрыть, кто из админов пишет, и участников групп", "mnt",
           buttons=_tool("ag"), refresh=True, project=True),
    Screen("cc", CLEAR, "удалить все посты в ваших каналах и скопировать заново", "mnt", buttons=_tool(
        "cc", check="ничего не удаляет: только показывает, что будет удалено",
        run="удалить то, что показала проверка; вернуть нельзя", danger=True,
    ), refresh=True, project=True),
    Screen("fail", FAILED, "посты, которые не удалось скопировать: повторить", "card", buttons=(
        Button("fail_all", "♻️ Повторить все", "скопировать заново все посты из списка"),
        Button("fail_clear", "🧽 Очистить список", "забыть эти посты, не копируя"),
    ), refresh=True, project=True, paged=True),
    Screen("mng", MANAGE, "как копировать посты и сам проект: имя, аккаунт, удаление", "card", buttons=(
        Button("p_edits", "✏️ Повторять правки", "исправили пост в источнике — исправить и копию", COPYING),
        Button("p_dels", "✂️ Повторять удаления", "удалили пост в источнике — удалить и копию", COPYING),
        Button("p_mode", "↔️ Как публиковать", "копия от имени вашего канала или пересылка «Переслано из»", COPYING),
        Button("p_link", "🔗 Запасная ссылка", "вместо ссылки на пост источника, если его копии у вас нет", COPYING),
        Button("p_dedup", "🧬 Без дублей", "не копировать в канал пост, который уже пришёл в него из "
                                            "другого источника", COPYING),
        Button("rename", "🏷 Переименовать", "новое имя проекта", PROJECT),
        Button("icon", "🎨 Значок", "эмодзи перед именем", PROJECT),
        Button("account", "👤 Аккаунт", "от чьего имени копируются посты", PROJECT),
        Button("delete", "🗑 Удалить проект", "остановить и убрать проект", PROJECT, DANGER),
    ), project=True),
    Screen("cfg", CONFIG, "все настройки одним файлом: скачать, заменить, вернуть", "mng", buttons=(
        Button("cfg_get", "📥 Скачать", "прислать файл с настройками"),
        Button("cfg_put", "📤 Загрузить", "заменить файл своим (сначала проверим)"),
        Button("cfg_undo", "↩️ Откатить", "вернуть настройки до последнего изменения"),
    ), project=True),
    Screen("acc", ACCOUNTS, "аккаунты Telegram, от имени которых копируются посты", "set", buttons=(
        Button("acc_login", "🔑 Войти по номеру", "номер → код из Telegram → пароль, если он есть"),
        Button("acc_upload", "📤 Загрузить сессию", "файл входа из Telegram Desktop или другого бота"),
    ), paged=True),
    Screen("acct", ACCOUNT, "один аккаунт", "acc", buttons=(
        Button("acc_del", "🗑 Удалить с сервера", "только если ни один проект его не использует", style=DANGER),
    )),
    Screen("chk", SELFCHECK, "всё ли на сервере на месте: бот, база, юниты, таймеры, проекты", "set",
           refresh=True),
    Screen("tsk", TASKS, "что сейчас работает и журналы", refresh=True, paged=True),
    Screen("unit", UNIT, "работает ли и что происходило", "tsk", refresh=True, project=True),
    Screen("set", SETTINGS, "аккаунты Telegram, присмотр за зеркалами, диагностика сервера", buttons=(
        Button("set_health", "🩺 Оповещение о сбоях", "каждые 10 минут: сообщить сюда, если зеркало падает снова и снова",
               WATCH),
        Button("set_restart", "🔁 Перезапуск по расписанию", "каждую ночь в 04:00 перезапускать зеркала", WATCH),
        Button("set_report", "📈 Сводка за неделю", "по понедельникам в 10:00: сколько скопировано, какие "
                                                    "направления молчат, где ошибки", WATCH),
    ), refresh=True),
)}

# Labels that aren't a screen's button: a form's choices, a list's rows, a
# notice's button. Same rules as the buttons (tests check them all).
TITLES = {
    "copy": "📋 Копия", "forward": "↪️ Пересылка",  # a direction's mode
    "hist_none": "⏭ Без истории", "hist_full": "📚 Вся история",  # 📜 История / ➕ Добавить
    "hist_last": "🔢 Последние N…", "hist_since": "📅 С даты…",
    "flt_add": "➕ Добавить фильтр", "flt_del": "🗑 Удалить фильтр",  # 🧹 Фильтры / 🧹 Фильтр
    "items_add": "➕ Добавить", "only_names": "📝 Только эти @…", "up": "⬆️ Выше", "down": "⬇️ Ниже",
    "advanced": "🔬 Тонкая настройка",  # 🧹 Фильтр: its rarely needed args
    "done": "✅ Готово",  # a list of channels being edited
    "dir_new": "➕ Новое направление",  # the heading of ➕ Добавить's steps
    # a channel picked from the admin's own Telegram (Bot API request_chat): the
    # prompt's button, then the two at the bottom (keyboards.menu.chat_picker)
    "pick": "📇 Выбрать из списка", "pick_channel": "📺 Канал", "pick_group": "👥 Группа",
    "resend": "📲 Отправить код заново",  # 🔑 Войти по номеру
    "notice": UNIT,  # a push notice: open the unit
}
# A list's rows start with these: the item they open (👤 an account) or
# remove (🗑 a value). Numbered lists (directions, filters) start with the number.
ROW_ACCOUNT, ROW_REMOVE = "👤", "🗑"
CHECKED, UNCHECKED = "☑️", "⬜"

# The colour of a label shown off a screen's buttons (a form's, a list's),
# whatever screen it is on: the same label, the same look.
LABEL_STYLES = {YES: SUCCESS, YES_DELETE: DANGER, TITLES["done"]: SUCCESS, TITLES["flt_del"]: DANGER}

MAIN_MENU = tuple(s.title for s in SCREENS.values() if not s.parent)
BY_TITLE = {s.title: s for s in SCREENS.values() if not s.parent}
ACTIONS = {b.action: (s.id, b) for s in SCREENS.values() for b in s.buttons}

# One emoji = one meaning across the bot: labels sharing an emoji share their
# first word's root (📁 Проекты / 📁 Проект, 🗑 Удалить / 🗑 Да, удалить) —
# except these verbs, the same action whatever the object, and ☑️ — a
# switch's state, not a meaning (tests check it).
SHARED_EMOJI = frozenset({"➕", "▶️", "⏹", CHECKED})


def children(screen_id: str) -> list:
    return [s for s in SCREENS.values() if s.parent == screen_id and s.id not in _NOT_LISTED]


# Opened from a list (a direction, a filter, a unit, an account) — not a › button.
_NOT_LISTED = frozenset({"card", "dir", "fv", "unit", "acct"})


def trail(screen_id: str) -> list:
    """The screen and its parents, the main-menu one first."""
    out: list = []
    while screen_id:
        out.insert(0, SCREENS[screen_id])
        screen_id = SCREENS[screen_id].parent
    return out


def title(action: str) -> str:
    """A button's label, for messages that name it."""
    return ACTIONS[action][1].title


def menu_path(action_or_screen: str) -> str:
    """"📁 Проекты → проект → ⚙️ Настройки проекта → 👤 Аккаунт" — where to find it."""
    if action_or_screen in SCREENS:
        parts = [s.title for s in trail(action_or_screen)]
    else:
        screen_id, button = ACTIONS[action_or_screen]
        parts = [s.title for s in trail(screen_id)] + [button.title]
    return " → ".join("проект" if p == CARD else p for p in parts)


def emoji_of(label: str) -> str:
    return label.split(" ", 1)[0].replace("️", "")


def unhandled_actions(handled) -> list:
    return sorted(set(ACTIONS) - set(handled))


def unknown_actions(handled) -> list:
    return sorted(set(handled) - set(ACTIONS))
