"""⚙️ Настройки проекта: what every direction of a project shares (edits,
deletes, mode, the fallback link) and the project itself (its buttons'
handlers: routers/projects.py); 📢 Рассылка (in 🔀 Направления): the
broadcast channel and where it goes."""

from typing import Any

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import configedit, configparse, registry, status, texts
from bot.callbacks import ActCB, NavCB
from bot.configstore import ConfigStore
from bot.keyboards.common import pick_kb
from bot.registry import TITLES, title
from bot.routers._common import input_kind, message_of, on_action, start_form
from bot.screens import show, view
from bot.sessions import account_label
from bot.states import Input, leave_form
from bot.texts import esc, head
from bot.writes import save
from telemirror.projects import Project

router = Router(name="params")

TOGGLES = {"p_edits": "disable_edit", "p_dels": "disable_delete", "p_mode": "mode"}
VALUES = {"p_bc": "broadcast_channel", "p_bct": "broadcast_targets", "p_link": "fallback_link_url",
          "p_dedup": "dedup_hours"}
CHAT_KEYS = ("broadcast_channel", "broadcast_targets")  # their prompt has 📇 Выбрать из списка
CHANNEL = (f"Нажмите {head(TITLES['pick'])}, перешлите сюда любой пост из канала или пришлите его ID "
           "(<code>-1001234567890</code>). <code>-</code> — убрать")
ASKS = {
    "broadcast_channel": f"Канал-рассылка: его посты копируются во все ваши каналы. {CHANNEL} (тогда — общий из "
                         "настроек сервера, если он задан).",
    "broadcast_targets": f"Куда копировать рассылку: нажмите {head(TITLES['pick'])}, перешлите пост из канала "
                         "или пришлите ID через запятую "
                         "(тема группы — <code>-1001234567890#5</code>). Список заменится целиком. "
                         "<code>-</code> — во все ваши каналы.",
    "fallback_link_url": "Ссылка (<code>https://t.me/yourchannel</code>), которой заменяются ссылки на чужие "
                         "закрытые каналы. <code>-</code> — убрать.",
    "dedup_hours": "Сколько часов помнить скопированные посты (например, <code>24</code>): пост, который за это "
                   "время уже пришёл в канал из другого источника, второй раз не копируется. Повтором считается "
                   "пост с тем же текстом и теми же фото и видео (пост без фото — с тем же текстом от 20 "
                   "символов); заново загруженные фото и видео — уже другие, их повтором не считают. "
                   "<code>0</code> или <code>-</code> — выключить.",
}


def value_text(data: Any, key: str, names: Any = texts.NO_NAMES) -> str:
    value = data.get(key)
    if value is None or value == []:
        return "не задано"
    if key == "broadcast_targets":
        return texts.refs(value, names)
    if key == "broadcast_channel":
        return texts.chat(value, names)
    return f"<code>{esc(value)}</code>"


def _params(project: Project) -> NavCB:
    return NavCB(s="mng", p=project.key)


SCREEN_OF = {"p_bc": "bc", "p_bct": "bc"}  # the rest are on ⚙️ Настройки проекта


def _back(project: Project, action: str) -> NavCB:
    return NavCB(s=SCREEN_OF.get(action, "mng"), p=project.key)


def _later(data: Any, keys: tuple, names: Any) -> list:
    """The note when a channel of ``keys`` isn't known by name yet."""
    refs = []
    for key in keys:
        value = data.get(key)
        refs += value if isinstance(value, list) else ([value] if value is not None else [])
    return [texts.NAMES_LATER] if texts.any_unnamed(refs, names) else []


def _own(data: Any, key: str) -> int:
    """How many directions have their own (hand-written) value of ``key``."""
    return sum(1 for d in configedit.directions(data) if key in d)


@view("mng")
async def manage_view(message: Message, edit: bool, nav: NavCB, *, project: Project, note: str = "",
                      **_) -> None:
    info = status.project_info(project)
    data = info.data
    titles = {
        "p_edits": f"{title('p_edits')}: {texts.on_off(not data.get('disable_edit', False))}",
        "p_dels": f"{title('p_dels')}: {texts.on_off(not data.get('disable_delete', False))}",
        "p_mode": f"{title('p_mode')}: {texts.mode_text(data.get('mode', 'copy'))}",
        "p_link": f"{title('p_link')}: " + ("задана" if data.get("fallback_link_url") else "нет"),
        "p_dedup": f"{title('p_dedup')}: " + (f"{esc(data['dedup_hours'])} ч" if data.get("dedup_hours")
                                              else texts.on_off(False)),
    }
    lines = [f"👤 Аккаунт: {esc(account_label(project.session))}"]
    if not info.writable:
        lines.append(texts.unreadable(info))
    elif data.get("fallback_link_url"):
        lines.append(f"{title('p_link')}: {value_text(data, 'fallback_link_url', info.names)}")
    own = {label: n for label, key in (("правки", "disable_edit"), ("удаления", "disable_delete"),
                                       ("режим", "mode"), ("ссылка", "fallback_link_url"),
                                       ("без повторов", "dedup_hours"))
           if (n := _own(data, key))}
    if own:
        lines.append("✳️ Свои значения в файле настроек (на них эти кнопки не действуют): "
                     + ", ".join(f"{label} — у {n} направл." for label, n in own.items()) + ".")
    more = (f"«{registry.COPYING}» — сразу для всех направлений проекта. Режим «{texts.MODES['forward']}» "
            f"нельзя включить, если общие фильтры меняют текст или картинки.\n"
            f"Служебное имя проекта: <code>{esc(project.key)}</code>")
    hidden = () if info.writable else ("p_edits", "p_dels", "p_mode", "p_link", "p_dedup")
    await show(message, edit, "mng", project, body="\n".join(lines), more=more, note=note, titles=titles,
               hidden=hidden, pg=nav.pg)


@view("bc")
async def broadcast_view(message: Message, edit: bool, nav: NavCB, *, project: Project, note: str = "",
                         **_) -> None:
    info = status.project_info(project)
    data = info.data
    lines = [
        f"{title('p_bc')}: {value_text(data, 'broadcast_channel', info.names)}",
        f"{title('p_bct')}: " + (value_text(data, "broadcast_targets", info.names)
                                 if data.get("broadcast_targets") else "во все ваши каналы"),
        *_later(data, ("broadcast_channel", "broadcast_targets"), info.names),
    ]
    body = "\n".join(lines) if info.writable else texts.unreadable(info)
    hidden = () if info.writable else ("p_bc", "p_bct")
    more = ("Каждый пост канала-рассылки копируется во все ваши каналы проекта (или только в выбранные). "
            "Удобно для общих объявлений.")
    await show(message, edit, "bc", project, body=body, more=more, note=note, hidden=hidden, pg=nav.pg)


@on_action(router, *TOGGLES)
async def on_toggle(callback: CallbackQuery, callback_data: ActCB, project: Project, store: ConfigStore,
                    deps: dict) -> None:
    await callback.answer()
    key = TOGGLES[callback_data.a]
    await save(message_of(callback), True, project,
               lambda p: store.update(p, lambda cfg: configedit.toggle_global(cfg, key)), _params(project), deps)


@on_action(router, *VALUES)
async def on_value(callback: CallbackQuery, callback_data: ActCB, project: Project, state: FSMContext) -> None:
    key = VALUES[callback_data.a]
    info = status.project_info(project)
    current = value_text(info.data, key, info.names)
    await start_form(callback, state, Input.value,
                     f"{head(title(callback_data.a))} — сейчас: {current}.\n\n{ASKS[key]}",
                     _back(project, callback_data.a), markup=pick_kb() if key in CHAT_KEYS else None,
                     data={"kind": "global", "p": project.key, "key": key, "a": callback_data.a})


@input_kind("global")
async def set_value(message: Message, state: FSMContext, raw: str, data: dict, project: Project,
                    store: ConfigStore, deps: dict, **_) -> None:
    key = data["key"]
    value: Any
    if raw == configparse.CLEAR:
        value = None
    elif key == "broadcast_channel":
        value = configparse.parse_channel_id(raw)
    elif key == "broadcast_targets":
        value = [configparse.yaml_ref(r) for r in configparse.parse_chat_refs(raw)]
    elif key == "dedup_hours":
        value = configparse.parse_hours(raw) or None  # 0: off, as removed
    else:
        value = configparse.parse_url(raw)
    await leave_form(message.chat.id, state)
    await save(message, False, project,
               lambda p: store.update(p, lambda cfg: configedit.set_global_value(cfg, key, value)),
               _back(project, data.get("a", "")), deps)
