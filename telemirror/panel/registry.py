"""The whole menu of the control panel, as data (after teleharvester's
``modules/registry.py``): screens, their buttons and what each does. The
keyboards, the screens' texts and the menu paths in messages are built from
here, so a button can't lose its description or its handler — the bot refuses
to start with a button nobody handles (``unhandled_actions``).

A screen's message lists each of its buttons with its hint; its keyboard has
them two short ones per row, then the screens opened from it (``›``), then
``🔄 Обновить`` and ``⬅️ Назад`` on the last row. Views (``screens.view``) add
the live content and their own rows (a list, values on buttons).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Button:
    action: str  # ActCB.a — the handler is registered for it (routers)
    title: str  # emoji + one or two words
    hint: str  # what it does: one line next to it in the screen's message


@dataclass(frozen=True)
class Screen:
    id: str  # NavCB.s
    title: str
    hint: str  # next to its button on the parent screen / in the /start message
    parent: str = ""  # its ⬅️ Назад; "" = a main-menu screen (reply keyboard)
    buttons: tuple = ()
    refresh: bool = False  # live state: 🔄 Обновить next to ⬅️ Назад
    project: bool = False  # one project's screen: its buttons carry the project key


# ── titles (button labels quote these, so a rename can't leave a stale one) ──
PROJECTS = "📁 Проекты"
TASKS = "📊 Задачи"
SETTINGS = "⚙️ Настройки"
CARD = "📁 Проект"
DIRECTIONS = "🔀 Направления"
DIRECTION = "🔀 Направление"
FILTERS = "🧹 Фильтры"
DIR_FILTERS = "🧹 Фильтры направления"
FILTER = "🧹 Фильтр"
PARAMS = "🔧 Параметры"
REPLAY = "⏪ Догрузка"
MAINTENANCE = "🛠 Обслуживание"
RESTRICT = "🔒 Запрет сохранения"
PINS = "📌 Закрепы"
ANONYMITY = "🕶 Анонимность"
ACCESS = "🛂 Доступ"
CLEAR = "🧨 Очистка каналов"
CONFIG = "🗂 Конфиг"
MANAGE = "🧰 Управление"
UNIT = "📊 Задача"
ACCOUNTS = "👤 Аккаунты"
ACCOUNT = "👤 Аккаунт"

BACK = "⬅️ Назад"
REFRESH = "🔄 Обновить"
CANCEL = "✖️ Отмена"
YES = "✅ Да"
YES_DELETE = "🗑 Да, удалить"
PREV, NEXT = "◀️", "▶️"

SCREENS = {s.id: s for s in (
    Screen("prj", PROJECTS, "зеркала: у каждого свой аккаунт, направления и сервис", buttons=(
        Button("new", "➕ Новый проект", "имя, значок и аккаунт — затем направления"),
    ), refresh=True),
    # a project's card and its screens, in the order of the work
    Screen("card", CARD, "направления, фильтры, параметры, догрузка, обслуживание", "prj", buttons=(
        Button("start", "▶️ Запустить", "живое зеркало проекта: пересылать новые сообщения"),
        Button("stop", "⏹ Остановить", "остановить зеркало проекта"),
        Button("restart", "🔁 Перезапустить", "перечитать конфигурацию — после правок"),
    ), refresh=True, project=True),
    Screen("dirs", DIRECTIONS, "откуда и куда пересылать: источники, получатели, режим", "card", buttons=(
        Button("dir_add", "➕ Добавить", "источник → получатели, режим и история"),
    ), project=True),
    Screen("dir", DIRECTION, "одно направление", "dirs", buttons=(
        Button("dir_src", "📨 Источники", "каналы, откуда берутся сообщения"),
        Button("dir_dst", "🎯 Получатели", "каналы, куда они пересылаются"),
        Button("dir_edits", "✏️ Правки", "повторять правки сообщений источника"),
        Button("dir_dels", "✂️ Удаления", "повторять удаления сообщений источника"),
        Button("dir_mode", "↔️ Режим", "копия от имени получателя или пересылка «Переслано из»"),
        Button("dir_delay", "⏱ Задержка", "пауза между отправками"),
        Button("dir_hist", "📜 История", "какую историю источника догружать"),
        Button("dir_rdelay", "⏱ Задержка догрузки", "пауза между отправками догрузки — только этого направления"),
        Button("dir_link", "🔗 Ссылка-замена", "своя для этого направления; без неё — общая из параметров"),
        Button("dir_del", "🗑 Удалить", "убрать направление из конфигурации"),
    ), project=True),
    Screen("dflt", DIR_FILTERS, "свои фильтры этого направления", "dir", project=True),
    Screen("flt", FILTERS, "общие фильтры: для направлений без своих", "card", project=True),
    Screen("fv", FILTER, "значения одного фильтра", "flt", project=True),
    Screen("par", PARAMS, "правки, удаления, режим по умолчанию; техканал, рассылка, ссылки", "card", buttons=(
        Button("p_edits", "✏️ Правки", "повторять правки — для направлений без своей настройки"),
        Button("p_dels", "✂️ Удаления", "повторять удаления — для направлений без своей настройки"),
        Button("p_mode", "↔️ Режим", "копия или пересылка — для направлений без своего режима"),
        Button("p_tech", "🛰 Техканал", "куда зеркало пишет предупреждения и ошибки"),
        Button("p_bc", "📢 Рассылка", "канал, посты которого уходят во все получатели"),
        Button("p_bct", "📬 Получатели рассылки", "куда идёт рассылка, если не во все получатели"),
        Button("p_link", "🔗 Ссылка-замена", "вместо ссылок, которые зеркало не может переписать"),
    ), project=True),
    Screen("rpl", REPLAY, "скопировать историю каналов, у направлений которых она задана", "card", buttons=(
        Button("rpl_start", "▶️ Начать", "зеркало проекта на это время остановится"),
        Button("rpl_stop", "⏹ Прервать", "в следующий раз продолжит с того же места"),
        Button("rpl_delay", "⏱ Задержка", "пауза между отправками догрузки — для всех направлений"),
    ), refresh=True, project=True),
    Screen("mnt", MAINTENANCE, "доступ к каналам, запрет сохранения, закрепы, анонимность, очистка", "card",
           project=True),
    Screen("ca", ACCESS, "видит ли аккаунт источники и может ли публиковать в получателях", "mnt", buttons=(
        Button("ca_dry", "🔍 Проверить", "ничего не меняет: только читает права аккаунта"),
        Button("ca_log", "📄 Журнал", "вывод последнего запуска"),
    ), refresh=True, project=True),
    Screen("rs", RESTRICT, "включить «Запрет копирования» во всех получателях", "mnt", buttons=(
        Button("rs_dry", "🔍 Проверить", "ничего не меняет: только показывает план"),
        Button("rs_run", "▶️ Выполнить", "после успешной проверки"),
        Button("rs_log", "📄 Журнал", "вывод последнего запуска"),
    ), refresh=True, project=True),
    Screen("sp", PINS, "перенести закрепы доноров на зеркала", "mnt", buttons=(
        Button("sp_dry", "🔍 Проверить", "ничего не меняет: только показывает план"),
        Button("sp_run", "▶️ Выполнить", "после успешной проверки с теми же флагами"),
        Button("sp_log", "📄 Журнал", "вывод последнего запуска"),
    ), refresh=True, project=True),
    Screen("ag", ANONYMITY, "анонимный админ и скрытые участники в группах аккаунта", "mnt", buttons=(
        Button("ag_dry", "🔍 Проверить", "ничего не меняет: только показывает план"),
        Button("ag_run", "▶️ Выполнить", "после успешной проверки"),
        Button("ag_log", "📄 Журнал", "вывод последнего запуска"),
    ), refresh=True, project=True),
    Screen("cc", CLEAR, "удалить все сообщения в получателях и начать заново", "mnt", buttons=(
        Button("cc_dry", "🔍 Проверить", "ничего не удаляет: только показывает, что будет удалено"),
        Button("cc_run", "▶️ Выполнить", "после успешной проверки; необратимо"),
        Button("cc_log", "📄 Журнал", "вывод последнего запуска"),
    ), refresh=True, project=True),
    Screen("cfg", CONFIG, "файл конфигурации: скачать, заменить, откатить", "card", buttons=(
        Button("cfg_get", "📥 Скачать", "текущий файл документом"),
        Button("cfg_put", "📤 Загрузить", "заменить файл своим (с проверкой)"),
        Button("cfg_undo", "↩️ Откатить", "вернуть версию до последнего изменения"),
    ), project=True),
    Screen("mng", MANAGE, "имя, значок, аккаунт, удаление проекта", "card", buttons=(
        Button("rename", "🏷 Переименовать", "новое имя проекта"),
        Button("icon", "🎨 Значок", "эмодзи перед именем"),
        Button("account", "👤 Аккаунт", "от чьего имени работает зеркало"),
        Button("delete", "🗑 Удалить проект", "остановить и убрать проект"),
    ), project=True),
    Screen("tsk", TASKS, "что выполняется: зеркала, догрузки, обслуживание; журналы", refresh=True),
    Screen("unit", UNIT, "состояние и журнал", "tsk", buttons=(
        Button("u_start", "▶️ Запустить", "запустить сервис"),
        Button("u_stop", "⏹ Остановить", "остановить сервис"),
        Button("u_restart", "🔁 Перезапустить", "перезапустить сервис"),
    ), refresh=True),
    Screen("set", SETTINGS, "аккаунты, доступ, мониторинг", buttons=(
        Button("set_health", "🩺 Проверка здоровья", "каждые 10 мин: сообщить, если зеркало падает по кругу"),
        Button("set_restart", "🔁 Перезапуск по расписанию", "каждый день в 04:00: перезапустить зеркала"),
    ), refresh=True),
    Screen("acc", ACCOUNTS, "сессии Telegram, от имени которых работают зеркала", "set", buttons=(
        Button("acc_login", "🔑 Войти по номеру", "номер → код → пароль 2FA, если есть"),
        Button("acc_upload", "📤 Загрузить сессию", "ZIP с tdata, .session с .json или .jsession"),
    )),
    Screen("acct", ACCOUNT, "одна сессия", "acc", buttons=(
        Button("acc_del", "🗑 Удалить", "только если ни один проект её не использует"),
    )),
)}

MAIN_MENU = tuple(s.title for s in SCREENS.values() if not s.parent)
BY_TITLE = {s.title: s for s in SCREENS.values() if not s.parent}
ACTIONS = {b.action: (s.id, b) for s in SCREENS.values() for b in s.buttons}

# One emoji = one meaning across the bot: labels sharing an emoji share their
# first word's root (📁 Проекты / 📁 Проект, 🗑 Удалить / 🗑 Да, удалить) —
# except these verbs, the same action whatever the object (tests check it).
SHARED_EMOJI = frozenset({"➕", "▶️", "⏹"})


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
    """"📁 Проекты → проект → 🧰 Управление → 👤 Аккаунт" — where to find it."""
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
