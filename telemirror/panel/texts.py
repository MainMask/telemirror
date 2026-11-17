"""Every user-facing string of the panel (Russian), in one place.

Handlers never hold UI text: edit wording here. Templates are HTML
(``parse_mode=HTML``); anything interpolated from outside — user names, ids,
journal lines, config values, error details — goes through ``esc()``.
"""

from datetime import datetime
from html import escape
from typing import Iterable, Optional


def esc(value: object) -> str:
    return escape(str(value), quote=False)


# ── reply keyboard / commands ───────────────────────────────────────────────
BTN_PROJECTS = "📁 Проекты"
BTN_TASKS = "📊 Задачи"
BTN_SETTINGS = "⚙️ Настройки"
REPLY_PLACEHOLDER = "Выберите раздел"

COMMANDS = {
    "start": "Главный экран",
    "status": "Что сейчас выполняется",
    "cancel": "Выйти из ввода или остановить задачу",
}

# ── common buttons ──────────────────────────────────────────────────────────
BTN_BACK = "⬅️ Назад"
BTN_REFRESH = "🔄 Обновить"
BTN_YES = "✅ Да"
BTN_NO = "✖️ Нет"
BTN_SAVE = "💾 Сохранить"
BTN_CANCEL = "✖️ Отмена"
BTN_PREV = "‹"
BTN_NEXT = "›"

# ── states ──────────────────────────────────────────────────────────────────
STATE_ICONS = {
    "active": "🟢",
    "reloading": "🟢",
    "activating": "🟡",
    "deactivating": "🟡",
    "inactive": "⚪️",
    "failed": "🔴",
}
MIRROR_STATE = {
    "active": "работает",
    "reloading": "работает",
    "activating": "запускается",
    "deactivating": "останавливается",
    "inactive": "остановлено",
    "failed": "сбой",
}
TASK_STATE = {
    "active": "выполняется",
    "reloading": "выполняется",
    "activating": "запускается",
    "deactivating": "останавливается",
    "inactive": "не выполняется",
    "failed": "завершилась с ошибкой",
}
NO_DATA = "нет данных"
NO_DATA_ICON = "⚪️"
UNKNOWN_COUNT = "—"


def state_icon(active: Optional[str]) -> str:
    return STATE_ICONS.get(active or "", NO_DATA_ICON)


def mirror_state(active: Optional[str]) -> str:
    return MIRROR_STATE.get(active or "", NO_DATA)


def task_state(active: Optional[str]) -> str:
    return TASK_STATE.get(active or "", NO_DATA)


def fmt_ts(ts: int) -> str:
    return datetime.fromtimestamp(ts).strftime("%d.%m %H:%M")


def fmt_duration(seconds: float) -> str:
    seconds = int(max(seconds, 0))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days} д {hours} ч"
    if hours:
        return f"{hours} ч {minutes} мин"
    return f"{minutes} мин"


def fmt_bytes(value: int) -> str:
    return f"{value / 1024 / 1024:.0f} МБ"


def on_off(value: bool) -> str:
    return "вкл" if value else "выкл"


# ── start screen ────────────────────────────────────────────────────────────
HOME = (
    "👋 Здравствуйте, <b>{name}</b>!\n\n"
    "Добро пожаловать в <b>Telemirror</b> — панель управления зеркалированием "
    "Telegram-каналов: направления, запуск и обслуживание.\n\n"
    "📁 Проектов: <b>{projects}</b> · 🔀 направлений: <b>{directions}</b> · "
    "{mirror_icon} зеркало: <b>{mirror}</b>\n\n"
    "📁 <b>Проекты</b> — ваши конфигурации зеркалирования: у каждой свои "
    "направления, параметры и способ запуска\n"
    "📊 <b>Задачи</b> — что сейчас выполняется: зеркало, replay истории и "
    "обслуживание; ход задач и их остановка\n"
    "⚙️ <b>Настройки</b> — источник конфигурации, доступ, мониторинг и "
    "обслуживание каналов (запрет сохранения, закрепы)\n\n"
    "/status — что сейчас выполняется · /cancel — выйти из ввода или остановить задачу\n\n"
    "<i>Выберите раздел в меню ниже</i> 👇"
)


def home(name: str, projects: int, directions: Optional[int], mirror_active: Optional[str]) -> str:
    return HOME.format(
        name=esc(name or "администратор"),
        projects=projects,
        directions=UNKNOWN_COUNT if directions is None else directions,
        mirror_icon=state_icon(mirror_active),
        mirror=mirror_state(mirror_active),
    )


# ── /cancel ─────────────────────────────────────────────────────────────────
CANCEL_INPUT = "Ввод отменён."
CANCEL_NOTHING = "Сейчас нечего отменять: ввода нет, задачи не выполняются."
CANCEL_PICK = "⏹ <b>Что остановить?</b>\n\nЖивое зеркало здесь не останавливается — это сервис, а не задача (см. «Задачи»)."

# ── units / projects ────────────────────────────────────────────────────────
UNIT_TITLES = {
    "live": "Живое зеркало",
    "crs": "Replay курсов",
    "rs": "Запрет сохранения",
    "sp": "Синхронизация закрепов",
}
PROJECT_TITLES = {"live": "Живое зеркало", "crs": "Курсы (история)"}
PROJECT_DESCR = {
    "live": "Пересылает новые сообщения круглосуточно. Изменения конфигурации "
    "вступают в силу после перезапуска.",
    "crs": "Разово копирует историю каналов (past_mode). Файл читается при каждом "
    "запуске replay; живое зеркало на это время останавливается.",
}
READ_ONLY = {
    "yaml_env": "🔒 Только просмотр: живое зеркало читает конфигурацию из переменной "
    "YAML_CONFIG_ENV, файл игнорируется. Меняйте её в .env вручную.",
    "env_mode": "🔒 Только просмотр: файла конфигурации нет, зеркало настроено "
    "переменными окружения (CHAT_MAPPING). Меняйте .env вручную.",
    "missing": "🔒 Файл конфигурации не найден.",
}
UNAPPLIED = (
    "⚠️ <b>Есть неприменённые изменения</b>: файл изменён после запуска зеркала. "
    "Нажмите «Применить» — иначе они вступят в силу при ежедневном перезапуске в 04:00."
)
LOAD_ERROR = "⚠️ Не удалось прочитать файл: <code>{error}</code>"

# ── tasks ───────────────────────────────────────────────────────────────────
TASKS_TITLE = "📊 <b>Задачи</b>\n\nЧто сейчас выполняется. Нажмите на строку — откроется карточка с журналом."
SYSTEMD_UNAVAILABLE = (
    "⚠️ systemd недоступен на этой машине — состояние сервисов не показывается и "
    "управлять ими нельзя. Панель рассчитана на VPS с systemd (deploy/README.md)."
)
UNIT_CARD = "{icon} <b>{title}</b>\n\nСостояние: <b>{state}</b>{sub}{since}{extra}"
UNIT_SINCE = "\nС {when} ({ago})"
UNIT_RESTARTS = "\nПерезапусков systemd: {n}"
UNIT_MEMORY = "\nПамять: {mem}"
UNIT_RESULT_FAILED = "\nРезультат последнего запуска: <b>{result}</b>"
UNIT_PROGRESS = "\n\n<b>Ход:</b> <code>{line}</code>"
UNIT_JOURNAL = "\n\n<b>Журнал последнего запуска</b> (до {n} строк):\n<pre>{journal}</pre>"
UNIT_JOURNAL_EMPTY = "\n\n<i>Журнал пуст.</i>"
BTN_RESTART = "🔄 Перезапустить"
BTN_START = "▶️ Запустить"
BTN_STOP = "⏹ Остановить"
BTN_TO_TASKS = "⬅️ К задачам"


def unit_line(title: str, active: Optional[str], live: bool) -> str:
    state = mirror_state(active) if live else task_state(active)
    return f"{state_icon(active)} {title} — {state}"


CONFIRM_RESTART_LIVE = (
    "🔄 <b>Перезапустить живое зеркало?</b>\n\n"
    "Конфигурация будет перечитана. На время перезапуска пересылка приостанавливается; "
    "при старте выполняется синхронизация broadcast-канала."
)
CONFIRM_STOP_LIVE = (
    "⏹ <b>Остановить живое зеркало?</b>\n\n"
    "Пересылка прекратится до ручного запуска. Ежедневный перезапуск в 04:00 "
    "остановленное зеркало не поднимает."
)
CONFIRM_START_LIVE = "▶️ <b>Запустить живое зеркало?</b>"
CONFIRM_START_LIVE_CONFLICT = (
    "▶️ <b>Запустить живое зеркало?</b>\n\n"
    "Сейчас выполняется «{task}» — systemd остановит её: у них общая сессия Telegram."
)
CONFIRM_START_COURSES = (
    "▶️ <b>Запустить replay курсов?</b>\n\n"
    "Живое зеркало будет остановлено на время replay (общая сессия Telegram) и "
    "запустится снова после успешного завершения. Ход виден в «Задачах»."
)
CONFIRM_STOP_TASK = (
    "⏹ <b>Остановить «{title}»?</b>\n\n"
    "Живое зеркало будет запущено снова."
)
CONFIRM_STOP_COURSES_NOTE = "\nReplay продолжится с чекпоинта при следующем запуске."
DONE_QUEUED = "Команда отправлена systemd."
COOLDOWN = (
    "Подождите ещё {sec} с: частые перезапуски расходуют лимит systemd "
    "(StartLimitBurst) и нагружают Telegram."
)
TASK_BUSY = "Уже выполняется «{title}». Дождитесь окончания или остановите её в «Задачах»."
SYSTEMD_ERROR = "Ошибка systemd: {detail}"
NOT_FOUND = "Экран устарел. Откройте раздел заново."

# ── projects ────────────────────────────────────────────────────────────────
PROJECTS_TITLE = (
    "📁 <b>Проекты</b>\n\n"
    "Конфигурации зеркалирования. У каждой свои направления, параметры и способ запуска."
)
PROJECTS_EMPTY = "\n\nНи одной конфигурации не найдено."


def project_button(title: str, count: Optional[int], active: Optional[str]) -> str:
    n = UNKNOWN_COUNT if count is None else count
    return f"{state_icon(active)} {title} · {n} напр."


PROJECT_CARD = (
    "📁 <b>{title}</b>\n{descr}\n\n"
    "Файл: <code>{path}</code>\n"
    "Сервис: <code>{unit}</code> — {state}\n"
    "Направлений: <b>{count}</b> (источников: {sources}, получателей: {targets})"
)
BTN_DIRECTIONS = "🔀 Направления"
BTN_FILTERS = "🧹 Фильтры"
BTN_PARAMS = "🔧 Параметры"
BTN_APPLY = "🔄 Применить (перезапуск)"
BTN_START_REPLAY = "▶️ Запустить replay"
BTN_STOP_REPLAY = "⏹ Остановить replay"
BTN_TO_PROJECTS = "⬅️ К проектам"
BTN_TO_PROJECT = "⬅️ К проекту"

DIRECTIONS_TITLE = "🔀 <b>Направления</b> · {project}\nСтраница {page}/{pages} · всего {count}"
DIRECTIONS_EMPTY = "\n\nНаправлений пока нет."
BTN_ADD = "➕ Добавить"
BTN_TO_LIST = "⬅️ К списку"
MARK_FORWARD = "forward"
MARK_HISTORY = "история"
MARK_FILTERS = "свои фильтры"
MARK_NO_EDIT = "без правок"
MARK_NO_DELETE = "без удалений"


def refs(values: Iterable[object]) -> str:
    return ", ".join(f"<code>{esc(v)}</code>" for v in values) or UNKNOWN_COUNT


def short_refs(values: list) -> str:
    if not values:
        return UNKNOWN_COUNT
    head = str(values[0])
    return head if len(values) == 1 else f"{head} +{len(values) - 1}"


DIRECTION_CARD = (
    "🔀 <b>Направление {n}</b> · {project}\n\n"
    "Из: {sources}\n"
    "В: {targets}\n"
    "Режим: <b>{mode}</b>{mode_src}\n"
    "Правки: {edit}{edit_src}\n"
    "Удаления: {delete}{delete_src}\n"
    "История (past_mode): {history}\n"
    "Фильтры: {filters}"
)
FROM_GLOBAL = " <i>(общая настройка)</i>"
FORWARDED = "пересылаются"
NOT_FORWARDED = "не пересылаются"
HISTORY_NONE = "нет"
HISTORY_FULL = "вся история"
HISTORY_LAST_N = "последние {n}"
HISTORY_SINCE = "с {date}"
FILTERS_GLOBAL = "общие"
BTN_TOGGLE_EDIT = "✏️ Правки: {state}"
BTN_TOGGLE_DELETE = "🗑 Удаления: {state}"
BTN_DELETE = "❌ Удалить"
CONFIRM_DELETE_DIRECTION = (
    "❌ <b>Удалить направление {n}?</b>\n\n"
    "Из: {sources}\nВ: {targets}\n\n"
    "Уже переданные сообщения останутся у получателей, но их правки и удаления "
    "больше не будут повторяться. Перед записью создаётся резервная копия .bak."
)

VALIDATING = "⏳ Проверяю конфигурацию тем же загрузчиком, что и при старте сервиса…"
SAVED = {
    "live": "✅ Сохранено. Чтобы изменения заработали, нажмите «Применить» в карточке проекта.",
    "crs": "✅ Сохранено. Изменения учтутся при следующем запуске replay.",
}
CONFIG_ERRORS = {
    "bad_ref": "Неверный ID канала: <code>{detail}</code>\nНужен формат "
    "<code>-1001234567890</code> или с темой <code>-1001234567890#5</code>.",
    "stale": "Список направлений изменился (возможно, файл правили вручную). "
    "Откройте экран заново.",
    "changed_on_disk": "Файл изменили вручную во время сохранения — ничего не записано. "
    "Откройте экран заново и повторите.",
    "duplicate": "Такая пара уже есть в конфигурации: <code>{detail}</code>",
    "self_loop": "Источник и получатель — один и тот же канал: <code>{detail}</code>",
    "bad_mode": "Неизвестный режим: <code>{detail}</code>",
    "read_only": "Этот проект доступен только для просмотра.",
    "roundtrip": "Панель не может безопасно переписать этот файл: в нём есть конструкции "
    "YAML, которые меняются при пересохранении. Правьте его вручную.",
    "invalid": "Конфигурация не прошла проверку — файл не изменён.\n<code>{detail}</code>",
}


def config_error(code: str, detail: str) -> str:
    template = CONFIG_ERRORS.get(code, "Ошибка: <code>{detail}</code>")
    return "⚠️ " + template.format(detail=esc(detail or code))


# ── add direction (FSM) ─────────────────────────────────────────────────────
ADD_HEADER = "➕ <b>Новое направление</b> · {project}\n\n"
ADD_SOURCE = (
    "Шаг 1. Отправьте ID <b>источника</b>: <code>-1001234567890</code> "
    "или с темой: <code>-1001234567890#5</code>.\n\n<i>/cancel — отменить</i>"
)
ADD_TARGETS = (
    "Источник: {source}\n\n"
    "Шаг 2. Отправьте ID <b>получателей</b> через запятую или с новой строки "
    "(можно с темой: <code>#5</code>).\n\n<i>/cancel — отменить</i>"
)
ADD_MODE = (
    "Источник: {source}\nПолучатели: {targets}\n\n"
    "Шаг 3. Режим пересылки:\n"
    "• <b>copy</b> — копия от имени получателя, работают все фильтры\n"
    "• <b>forward</b> — пересылка с подписью «Переслано из»; фильтры, меняющие "
    "содержимое, с ним недопустимы"
)
ADD_HISTORY = (
    "Источник: {source}\nПолучатели: {targets}\nРежим: <b>{mode}</b>\n\n"
    "Шаг 4. Скопировать историю источника (past_mode: full_history)?\n\n"
    "<i>Для живого зеркала историю копирует отдельный запуск "
    "<code>python past_mode.py</code> (в панели — в следующей версии).</i>"
)
ADD_SUMMARY = (
    "Проверьте направление:\n\n"
    "Из: {source}\nВ: {targets}\nРежим: <b>{mode}</b>\nИстория: {history}\n\n"
    "При сохранении конфигурация проверяется тем же загрузчиком, что и при старте сервиса."
)
BTN_MODE_COPY = "copy"
BTN_MODE_FORWARD = "forward"
BTN_HISTORY_NONE = "Без истории"
BTN_HISTORY_FULL = "Вся история"
ADD_EXPIRED = "Ввод устарел — начните добавление заново."

# ── filters / params ────────────────────────────────────────────────────────
FILTERS_TITLE = "🧹 <b>Фильтры</b> · {project}\n\n<b>Общие</b> (для направлений без своих фильтров):\n{filters}"
FILTERS_NONE = "— нет"
FILTERS_OWN = "\n\nНаправлений со своими фильтрами: <b>{n}</b> (видны в карточке направления)."
FILTERS_HINT = "\n\n<i>Фильтры пока меняются вручную в файле; в панели — только просмотр.</i>"
PARAMS_TITLE = (
    "🔧 <b>Параметры</b> · {project}\n\n"
    "Общие настройки — действуют для направлений, где они не заданы явно:\n"
    "• Пересылать правки: <b>{edit}</b>\n"
    "• Пересылать удаления: <b>{delete}</b>\n"
    "• Режим: <b>{mode}</b>\n\n"
    "<i>Режим forward не пройдёт проверку, если общие фильтры меняют содержимое.</i>"
)
BTN_PARAM_EDIT = "✏️ Правки: {state}"
BTN_PARAM_DELETE = "🗑 Удаления: {state}"
BTN_PARAM_MODE = "🔁 Режим: {mode}"

# ── settings / maintenance ──────────────────────────────────────────────────
SETTINGS_TITLE = (
    "⚙️ <b>Настройки</b>\n\n"
    "<b>Конфигурация живого зеркала:</b> {source}\n"
    "<b>Администраторы панели:</b> {admins}\n"
    "<b>Технический канал</b> (алерты, TECH_CHANNEL): {tech}\n"
    "<b>Мониторинг:</b>\n"
    "• проверка здоровья каждые 10 мин — {health}\n"
    "• ежедневный перезапуск в 04:00 — {restart}\n\n"
    "<i>Доступ и токен задаются в .env (PANEL_ADMIN_IDS, PANEL_BOT_TOKEN); "
    "панель их не меняет и секреты не показывает.</i>"
)
SOURCE_FILE = "файл <code>.configs/mirror.config.yml</code> (правится из панели)"
SOURCE_YAML_ENV = "переменная YAML_CONFIG_ENV (только просмотр)"
SOURCE_ENV = "переменные окружения CHAT_MAPPING (только просмотр)"
TECH_SET = "задан"
TECH_UNSET = "не задан — алерты никуда не отправляются"
TIMER_ON = "включена"
TIMER_OFF = "выключена"
BTN_MAINTENANCE = "🛠 Обслуживание"
BTN_TO_SETTINGS = "⬅️ К настройкам"
BTN_TO_MAINTENANCE = "⬅️ К обслуживанию"

MAINTENANCE_TITLE = (
    "🛠 <b>Обслуживание</b>\n\n"
    "Операции с каналами от имени аккаунта зеркала. Им нужна общая сессия Telegram, "
    "поэтому на время выполнения живое зеркало останавливается и запускается снова "
    "по завершении.\n\n"
    "Сначала всегда выполняется проверка (dry-run): она ничего не меняет и выводит план."
)
BTN_RS = "🔒 Запрет сохранения"
BTN_SP = "📌 Закрепы"
RS_TITLE = (
    "🔒 <b>Запрет сохранения</b>\n\n"
    "Включает «Запрет копирования» (noforwards) во всех каналах-получателях живого "
    "зеркала и курсов. Где он уже включён — пропускается.\n\n"
    "Последний запуск: {last}"
)
SP_TITLE = (
    "📌 <b>Синхронизация закрепов</b>\n\n"
    "Копирует закреплённые сообщения доноров на их зеркала (нужна БД Postgres: связи "
    "берутся из таблицы binding_id). По умолчанию снимает закрепы, которые снял донор, "
    "— только у сообщений, созданных зеркалом.\n\n"
    "Последний запуск: {last}"
)
SP_FLAGS = {
    "--additive": "Только добавлять (не снимать)",
    "--allow-clear": "Снимать все, если у донора закрепов нет",
    "--include-broadcast": "Включая broadcast-канал",
    "--thorough": "Тщательно: опрашивать каждую тему",
}
BTN_DRY_RUN = "🔍 Проверить (dry-run)"
BTN_RUN_RS = "▶️ Включить"
BTN_RUN_SP = "▶️ Выполнить"
BTN_OUTPUT = "📄 Вывод последнего запуска"
LAST_NEVER = "в этой сессии панели не запускался"
LAST_RUN = "{kind} — {state}, {when}"
KIND_DRY = "проверка"
KIND_REAL = "выполнение"
RUN_NEEDS_DRY = "Сначала выполните проверку (dry-run) с теми же параметрами и дождитесь её успешного завершения."
CONFIRM_RUN = (
    "{title}: <b>{kind}</b>?\n\n{what}\n\n"
    "Живое зеркало будет остановлено на время задачи и запущено снова по её завершении."
)
WHAT_DRY = "Проверка ничего не меняет — только выводит план."
WHAT_REAL = "⚠️ Будут внесены изменения в каналы."
TASK_STARTED = "Задача запущена. Ход и вывод — в «Задачах»."
RESULT_RUNNING = "выполняется"
RESULT_OK = "успешно"
RESULT_FAIL = "ошибка ({result})"
