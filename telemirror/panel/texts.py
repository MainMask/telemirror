"""User-facing text shared by several routers (Russian, HTML). Button labels
and screen hints live in ``registry``; a form's prompts are constants of its
router. Anything interpolated from outside — names, ids, journal lines, config
values, error details — goes through ``esc()``."""

from datetime import datetime
from typing import Iterable, Optional

from telemirror.panel import screens
from telemirror.panel.registry import menu_path
from telemirror.panel.screens import esc

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


def refs(values: Iterable[object]) -> str:
    return ", ".join(f"<code>{esc(v)}</code>" for v in values) or UNKNOWN


def short_refs(values: list) -> str:
    if not values:
        return UNKNOWN
    head = str(values[0])
    return head if len(values) == 1 else f"{head} +{len(values) - 1}"


def history_text(pm) -> str:
    if not isinstance(pm, dict) or not pm:
        return "нет"
    if pm.get("full_history"):
        return "вся история"
    if pm.get("last_n") is not None:
        return f"последние {esc(pm['last_n'])}"
    if pm.get("since_date") is not None:
        return f"с {esc(pm['since_date'])}"
    return "нет"


# ── common refusals / notes ─────────────────────────────────────────────────
STALE_BUTTON = "Кнопка устарела — откройте раздел заново."
NO_PROJECT = screens.NO_PROJECT
CONFIRM_EXPIRED = "Подтверждение устарело — нажмите кнопку заново."
# a project whose .jsession was removed by hand
SESSION_MISSING = f"⛔ Файл сессии проекта не найден. Выберите аккаунт: {menu_path('account')}."
CANCELLED = "Отменено."
SYSTEMD_UNAVAILABLE = (
    "⚠️ systemd недоступен на этой машине — состояние сервисов не показывается и "
    "управлять ими нельзя. Панель рассчитана на VPS с systemd (deploy/README.md)."
)
SYSTEMD_ERROR = "⚠️ Ошибка systemd: {detail}"
COOLDOWN = (
    "⛔ Подождите ещё {sec} с: частые перезапуски расходуют лимит systemd "
    "(StartLimitBurst) и нагружают Telegram."
)
VALIDATING = "⏳ Проверяю конфигурацию тем же загрузчиком, что и при старте сервиса…"
SAVED = "✅ Сохранено. Чтобы изменения заработали, нажмите «🔁 Перезапустить» в карточке проекта."
SAVED_STOPPED = "✅ Сохранено. Изменения учтутся при следующем запуске."
INTERNAL_ERROR = (
    "⚠️ Внутренняя ошибка панели (<code>{error}</code>). Подробности — в журнале "
    "<code>journalctl -u telemirror-panel</code>. Откройте раздел заново."
)

READ_ONLY = {"missing": "🔒 Файл конфигурации не найден."}

CONFIG_ERRORS = {
    "bad_ref": "Неверный ID канала: <code>{detail}</code>\nНужен формат "
    "<code>-1001234567890</code> или с темой <code>-1001234567890#5</code>.",
    "stale": "Список изменился (возможно, файл правили вручную). Откройте экран заново.",
    "changed_on_disk": "Файл изменили вручную во время сохранения — ничего не записано. "
    "Откройте экран заново и повторите.",
    "duplicate": "Такая пара уже есть в конфигурации: <code>{detail}</code>",
    "self_loop": "Источник и получатель — один и тот же канал: <code>{detail}</code>",
    "bad_mode": "Неизвестный режим: <code>{detail}</code>",
    "read_only": "Файл конфигурации не найден — менять нечего.",
    "roundtrip": "Панель не может безопасно переписать этот файл: в нём есть конструкции "
    "YAML, которые меняются при пересохранении. Правьте его вручную.",
    "invalid": "Конфигурация не прошла проверку — файл не изменён.\n<code>{detail}</code>",
    "no_backup": "Резервной копии (.bak) нет — откатывать нечего.",
    "bad_yaml": "Это не конфигурация telemirror: <code>{detail}</code>",
    "too_big": "Файл слишком большой (максимум {detail}).",
    "bad_url": "Нужна ссылка вида <code>https://t.me/channel</code>, получено: <code>{detail}</code>",
    "bad_number": "Неверное число: <code>{detail}</code>",
    "bad_date": "Нужна дата <code>2024-01-31</code> или <code>2024-01-31T12:00:00</code>, "
    "получено: <code>{detail}</code>",
    "bad_item": "Пустое или слишком длинное значение (до 200 символов): <code>{detail}</code>",
    "bad_filter": "Этот фильтр нельзя менять из панели: <code>{detail}</code>",
    "bad_pair": "Нужна строка вида <code>что => на что</code>, получено: <code>{detail}</code>",
    "no_history": "Ни у одного направления не задана история — задержку догрузки ставить некуда.",
}


def config_error(code: str, detail: str = "") -> str:
    template = CONFIG_ERRORS.get(code, "Ошибка: <code>{detail}</code>")
    return "⚠️ " + template.format(detail=esc(detail or code))


DIFF_TITLE = "<b>Что изменится</b> (было → станет):\n<pre>{diff}</pre>"
DIFF_SAME = "<i>Содержимое не отличается от текущего.</i>"
DIFF_TRUNCATED = "\n… (показано начало)"
