"""User-facing text shared by several routers (Russian, HTML). Button labels
and screen hints live in ``registry``; a form's prompts are constants of its
router. Anything interpolated from outside — names, ids, journal lines, config
values, error details — goes through ``esc()``.

Icons: ⛔ — refused (nothing done), ⚠️ — an error or a warning, ✅ — done."""

from datetime import date, datetime, time, timezone
from html import escape
from types import MappingProxyType
from typing import Iterable, Mapping, Optional

from bot import settings
from bot.registry import TITLES, menu_path, title
from telemirror.projects import Project


def esc(value: object) -> str:
    return escape(str(value), quote=False)


def head(label: str) -> str:
    return f"<b>{esc(label)}</b>"


def more(text: str) -> str:
    """How it works, the details: folded under the screen, opened by a tap
    (HTML ``text``)."""
    return f"<blockquote expandable>{text}</blockquote>"


def cut(text: str, limit: int) -> str:
    """A label shortened for a button: whole up to ``limit``, else cut with «…»."""
    return text if len(text) <= limit else text[: limit - 1] + "…"


def project_label(project: Project) -> str:
    return f"{project.icon} {project.name}"


# ── a project's units (Project.units order: live, past, task) ───────────────
UNIT_KINDS = ("зеркало", "копирование истории", "инструмент")


def unit_kind(project: Project, unit: str) -> int:
    return project.units.index(unit)


def unit_label(project: Project, unit: str) -> str:
    return f"{project_label(project)} · {UNIT_KINDS[unit_kind(project, unit)]}"


# ── a direction's mode (config ``mode:``): the words of its choice buttons ──
MODES = {mode: TITLES[mode].split(" ", 1)[1].lower() for mode in ("copy", "forward")}


def mode_text(mode: object) -> str:
    return MODES.get(str(mode), esc(mode))

# ── states ──────────────────────────────────────────────────────────────────
STATE_ICONS = {
    "active": "🟢", "reloading": "🟢",
    "activating": "🟡", "deactivating": "🟡",
    "inactive": "⚪️", "failed": "🔴",
}
MIRROR_STATE = {
    "active": "работает", "reloading": "работает",
    "activating": "запускается", "deactivating": "останавливается",
    "inactive": "остановлено", "failed": "сбой",
}
TASK_STATE = {
    "active": "выполняется", "reloading": "выполняется",
    "activating": "запускается", "deactivating": "останавливается",
    "inactive": "не выполняется", "failed": "завершилась с ошибкой",
}
NO_DATA = "нет данных"
UNKNOWN = "—"


def state_icon(active: Optional[str]) -> str:
    return STATE_ICONS.get(active or "", "⚪️")


def mirror_state(active: Optional[str]) -> str:
    return MIRROR_STATE.get(active or "", NO_DATA)


def task_state(active: Optional[str]) -> str:
    return TASK_STATE.get(active or "", NO_DATA)


def on_off(value: bool) -> str:
    return "вкл" if value else "выкл"


def fmt_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, settings.TIMEZONE).strftime("%d.%m %H:%M")


def fmt_date(value: object) -> str:
    """A config's ``since_date`` (an ISO string, a date or a datetime) as typed in
    ⏪ 📅 С даты…: ``31.01.2024``, ``31.01.2024 12:00`` — Moscow time. One without
    an offset (hand-written) is UTC to the mirror (Telethon's offset_date), so
    it's shown so: ``2024-01-31`` → ``31.01.2024 03:00``."""
    try:
        if isinstance(value, datetime):
            moment = value
        elif isinstance(value, date):
            moment = datetime.combine(value, time())
        else:
            moment = datetime.fromisoformat(str(value))
    except ValueError:
        return esc(value)
    moment = moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
    moment = moment.astimezone(settings.TIMEZONE)
    return moment.strftime("%d.%m.%Y" if moment.time() == time() else "%d.%m.%Y %H:%M")


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


# ── channels: by their titles (``projects/<key>/chats.json``), else by id ────
Names = Mapping[int, str]
NO_NAMES: Names = MappingProxyType({})
NAMES_LATER = ("<i>Каналы без названия покажутся по имени после запуска зеркала или проверки: "
               f"{esc(menu_path('ca'))}.</i>")


def _split(ref: object) -> tuple:
    """``-100…#5`` → (-100…, "5"); a bad one → (None, "")."""
    chat, _, topic = str(ref).strip().partition("#")
    try:
        return int(chat), topic
    except ValueError:
        return None, ""


def named(ref: object, names: Names) -> bool:
    return _split(ref)[0] in names


def chat(ref: object, names: Names = NO_NAMES) -> str:
    """A channel for a message: «<b>Название</b>», or its id when unknown."""
    chat_id, topic = _split(ref)
    if chat_id in names:
        text = f"<b>{esc(names[chat_id])}</b>"
        return text + (f" · тема {esc(topic)}" if topic else "")
    return f"<code>{esc(ref)}</code>"


def chat_plain(ref: object, names: Names = NO_NAMES, limit: int = 24) -> str:
    """A channel for a button (no HTML): its title cut to ``limit``, else its id."""
    chat_id, topic = _split(ref)
    if chat_id not in names:
        return str(ref)
    return cut(names[chat_id], limit) + (f" #{topic}" if topic else "")


def refs(values: Iterable[object], names: Names = NO_NAMES) -> str:
    return ", ".join(chat(v, names) for v in values) or UNKNOWN


def short_refs(values: list, names: Names = NO_NAMES) -> str:
    if not values:
        return UNKNOWN
    head = chat_plain(values[0], names)
    return head if len(values) == 1 else f"{head} +{len(values) - 1}"


def any_unnamed(values: Iterable[object], names: Names) -> bool:
    return any(not named(v, names) for v in values)


def history_text(pm) -> str:
    if not isinstance(pm, dict) or not pm:
        return "нет"
    if pm.get("full_history"):
        return "вся история"
    if pm.get("last_n") is not None:
        return f"последние {esc(pm['last_n'])}"
    if pm.get("since_date") is not None:
        return f"с {fmt_date(pm['since_date'])}"
    return "нет"


def pace_text(drip) -> str:
    """``past_mode.drip`` in words; None — all at once."""
    if not isinstance(drip, dict):
        return "сразу"
    if "seconds" in drip:
        return f"1 пост раз в {esc(drip.get('seconds'))} с"
    posts = drip.get("posts")
    word = ("пост" if posts % 10 == 1 and posts % 100 != 11
            else "поста" if 2 <= posts % 10 <= 4 and not 12 <= posts % 100 <= 14
            else "постов") if isinstance(posts, int) else "постов"
    return f"{esc(posts)} {word} за {esc(drip.get('minutes'))} мин"


# systemd's Result= of a stopped unit, in words
RESULTS = {
    "success": "успешно", "exit-code": "завершилось с ошибкой", "signal": "прервано",
    "core-dump": "аварийно завершилось", "timeout": "не уложилось во время",
    "watchdog": "зависло и было перезапущено", "start-limit-hit": "слишком много сбоев подряд",
    "oom-kill": "не хватило памяти", "resources": "не удалось запустить",
}


def result_text(result: object) -> str:
    return RESULTS.get(str(result), esc(result))


# ── common refusals / notes ─────────────────────────────────────────────────
STALE_BUTTON = "Кнопка устарела — откройте раздел заново."
PICK_ASK = (f"Нажмите внизу «{TITLES['pick_channel']}» или «{TITLES['pick_group']}» и выберите из списка 👇\n"
            "<i>В списке — каналы и группы вашего Telegram. Нет нужного — перешлите сюда пост из него "
            "или пришлите ID.</i>")
PICKED = "📇 Выбрано: <b>{title}</b>"
PICK_LATE = "Канал сейчас не нужен — выбор не применён."
PICK_CLOSED = "📇 Выбор из списка закрыт — внизу снова меню."
NO_PROJECT = "⛔ Проект не найден — возможно, его удалили."
CONFIRM_EXPIRED = "Подтверждение устарело — нажмите кнопку заново."
# a project whose .jsession was removed by hand
SESSION_MISSING = f"⛔ Вход в аккаунт проекта не найден. Выберите аккаунт: {menu_path('account')}."
CONFIG_MISSING = "⛔ Файл настроек проекта не найден."
CANCELLED = "Отменено."
SEND_AGAIN = "Пришлите ещё раз:"
NEED_TEXT = "Нужен текст. " + SEND_AGAIN
USE_BUTTONS = "Выберите вариант кнопкой выше — или /cancel, чтобы выйти."
USE_MENU = "Выберите раздел в меню ниже 👇"
COMMAND_SENT = "Команда отправлена."
SYSTEMD_UNAVAILABLE = (
    "⚠️ Запускать и останавливать здесь нельзя: панель должна работать на сервере (VPS), "
    "где установлено зеркало."
)
SYSTEMD_ERROR = "⚠️ Не удалось выполнить команду на сервере: {detail}"
COOLDOWN = "⛔ Подождите ещё {sec} с: слишком частые перезапуски сервер блокирует, а Telegram ограничивает."
VALIDATING = "⏳ Проверяю настройки…"
SELFCHECK_WAIT = "⏳ Проверяю установку… Это займёт несколько секунд."
SELFCHECK_MORE = (
    "✅ в порядке · ⚠️ стоит посмотреть · ❌ не будет работать · ⚪ выключено вами. "
    "Только смотрит: ничего не запускает и не меняет. Аккаунты проектов к Telegram не подключаются "
    "(зеркало уже держит ту же сессию, второе подключение может её погубить) — проверяется только файл. "
    "То же на сервере: <code>python -m telemirror.selfcheck</code>."
)
SAVED = f"✅ Сохранено. Чтобы изменения заработали, нажмите «{title('restart')}» в карточке проекта."
SAVED_STOPPED = "✅ Сохранено. Изменения учтутся при следующем запуске."
INTERNAL_ERROR = (
    "⚠️ Что-то пошло не так (<code>{error}</code>). Откройте раздел заново; если повторится — "
    "подробности в журнале панели на сервере: <code>journalctl -u telemirror-panel</code>."
)

CONFIG_ERRORS = {
    "bad_ref": "Не похоже на канал: <code>{detail}</code>\nПерешлите сюда любой пост из канала "
    "или пришлите его ID: <code>-1001234567890</code> (тема группы — <code>-1001234567890#5</code>).",
    "stale": "Список изменился (возможно, настройки меняли в файле). Откройте экран заново.",
    "changed_on_disk": "Файл настроек изменили во время сохранения — ничего не записано. "
    "Откройте экран заново и повторите.",
    "duplicate": "Такое направление уже есть: <code>{detail}</code>. Откройте его в списке направлений.",
    "self_loop": "Канал не может копировать сам в себя: <code>{detail}</code>",
    "bad_mode": "Неизвестный режим: <code>{detail}</code>",
    "read_only": "Файл настроек проекта не найден — менять нечего.",
    "roundtrip": "Этот файл настроек написан вручную так, что панель не может его безопасно "
    f"изменить. Правьте его в файле: {esc(menu_path('cfg_get'))}.",
    "invalid": "Настройки не прошли проверку — ничего не изменено.\n<code>{detail}</code>",
    "no_backup": "Прошлой версии нет — возвращать нечего.",
    "bad_yaml": "Это не файл настроек зеркала: <code>{detail}</code>",
    "too_big": "Файл слишком большой (максимум {detail}).",
    "bad_url": "Нужна ссылка вида <code>https://t.me/channel</code>, получено: <code>{detail}</code>",
    "bad_number": "Нужно число, например <code>3</code> или <code>0.5</code>, получено: <code>{detail}</code>",
    "bad_delay": "Нужно число секунд от 0 до 60, например <code>1.5</code>, получено: <code>{detail}</code>",
    "bad_hours": "Нужно число часов от 0 до 720 (30 дней), например <code>24</code>, получено: "
    "<code>{detail}</code>",
    "bad_last_n": "Нужно целое число от 1 до 1 000 000, например <code>100</code>, получено: <code>{detail}</code>",
    "bad_max_pins": f"Нужно целое число от {settings.SYNC_PINS_MAX_PINS[0]} до {settings.SYNC_PINS_MAX_PINS[1]}, "
    f"например <code>{settings.SYNC_PINS_DEFAULT_MAX_PINS}</code>, получено: " "<code>{detail}</code>",
    "bad_date": "Нужна дата <code>31.01.2024</code> или с временем <code>31.01.2024 12:00</code>, "
    "получено: <code>{detail}</code>",
    "bad_item": "Значение пустое или длиннее 200 символов: <code>{detail}</code>. Каждое значение — с новой "
    "строки, до 200 символов.",
    "bad_text": "Слишком длинный текст (больше 1000 символов): <code>{detail}</code>",
    "bad_filter": "Этот фильтр меняется только в файле настроек: <code>{detail}</code>. Скачать файл: "
    f"{esc(menu_path('cfg_get'))}.",
    "bad_pair": "Нужна строка вида <code>что => на что</code>, например <code>купить => приобрести</code>, "
    "каждая пара с новой строки. Получено: <code>{detail}</code>",
    "bad_pace": "Нужно «сколько постов / за сколько минут», например <code>5/45</code> "
    "(1–100 постов, 1–1440 минут), или раз во сколько секунд, например <code>30с</code> "
    "(1–86400 секунд), получено: <code>{detail}</code>",
    "no_history": f"Не выбрано, какие старые посты копировать: {menu_path('rpl_hist')}.",
    "no_directions": f"В проекте нет направлений — сначала добавьте: {esc(menu_path('dir_add'))}.",
    "no_refs": "В списке должен остаться хотя бы один канал: сначала добавьте другой, потом уберите этот.",
    "not_channel": "По этому сообщению канал не определить: оно переслано не из канала (или его автор "
    "скрыл, откуда оно). Перешлите пост из самого канала или пришлите ID канала.",
}


def unreadable(info) -> str:
    """Why a project's config can't be shown (``status.ProjectInfo``): said in
    place of its screen's content."""
    if info.missing:
        return CONFIG_MISSING
    return f"⚠️ Не удалось прочитать файл настроек: <code>{esc((info.error or '')[:300])}</code>"


def config_error(code: str, detail: str = "") -> str:
    template = CONFIG_ERRORS.get(code, "Ошибка: <code>{detail}</code>")
    return "⚠️ " + template.format(detail=esc(detail or code))


def retry(code: str, detail: str = "") -> str:
    """A refused typed value: why, and the same step again."""
    return f"{config_error(code, detail)}\n{SEND_AGAIN}"


DIFF_TITLE = "<b>Что изменится</b> (было → станет):\n<pre>{diff}</pre>"
DIFF_SAME = "<i>Содержимое не отличается от текущего.</i>"
DIFF_TRUNCATED = "\n… (показано начало)"
