"""🔧 Параметры: a project's defaults (edits, deletes, mode — for directions
without their own) and its channels and links (tech channel, broadcast,
fallback link)."""

from typing import Any

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from telemirror.panel import configstore, status, texts
from telemirror.panel.callbacks import ActCB, NavCB
from telemirror.panel.configstore import ConfigError, ConfigStore
from telemirror.panel.registry import title
from telemirror.panel.routers._common import input_kind, leave_form, message_of, on_action, project_of, start_form
from telemirror.panel.routers.directions import MODES
from telemirror.panel.screens import esc, head, show, view
from telemirror.panel.states import Input
from telemirror.panel.systemd import Systemd
from telemirror.panel.writes import save
from telemirror.projects import Project

router = Router(name="params")

TOGGLES = {"p_edits": "disable_edit", "p_dels": "disable_delete", "p_mode": "mode"}
VALUES = {"p_tech": "tech_channel", "p_bc": "broadcast_channel", "p_bct": "broadcast_targets",
          "p_link": "fallback_link_url"}
ASKS = {
    "tech_channel": "пришлите ID технического канала (<code>-1001234567890</code>) или <code>-</code>, "
                    "чтобы убрать (тогда берётся TECH_CHANNEL из .env).",
    "broadcast_channel": "пришлите ID канала рассылки (<code>-1001234567890</code>) или <code>-</code>, "
                         "чтобы убрать (тогда берётся BROADCAST_CHANNEL из .env).",
    "broadcast_targets": "пришлите ID получателей рассылки через запятую (можно с темой <code>#5</code>) "
                         "или <code>-</code>, чтобы слать во все получатели зеркала.",
    "fallback_link_url": "пришлите ссылку (<code>https://t.me/yourchannel</code>) или <code>-</code>, "
                         "чтобы убрать.",
}


def value_text(data: Any, key: str) -> str:
    value = data.get(key)
    if value is None or value == []:
        return "не задано"
    return texts.refs(value) if key == "broadcast_targets" else f"<code>{esc(value)}</code>"


@view("par")
async def params_view(message: Message, edit: bool, nav: NavCB, state: FSMContext, note: str = "", **_) -> None:
    project = status.find(nav.p)
    if project is None:
        await message.answer(texts.NO_PROJECT)
        return
    await show_params(message, edit, project, note)


async def show_params(message: Message, edit: bool, project: Project, note: str = "") -> None:
    info = status.project_info(project)
    data = info.data
    titles = {
        "p_edits": f"{title('p_edits')}: {texts.on_off(not data.get('disable_edit', False))}",
        "p_dels": f"{title('p_dels')}: {texts.on_off(not data.get('disable_delete', False))}",
        "p_mode": f"{title('p_mode')}: {MODES.get(str(data.get('mode', 'copy')), data.get('mode'))}",
    }
    body = "\n".join([
        f"🛰 Техканал: {value_text(data, 'tech_channel')}",
        f"📢 Рассылка: {value_text(data, 'broadcast_channel')}",
        f"📬 Получатели рассылки: {value_text(data, 'broadcast_targets')}",
        f"🔗 Ссылка-замена: {value_text(data, 'fallback_link_url')}",
        "<i>Режим «пересылка» не пройдёт проверку, если общие фильтры меняют содержимое.</i>",
    ])
    if not info.writable:
        body = texts.READ_ONLY.get(info.read_only or "", "") or f"⚠️ <code>{esc(info.error or '')}</code>"
    hidden = () if info.writable else tuple(TOGGLES) + tuple(VALUES)
    await show(message, edit, "par", project, body=body, note=note, titles=titles, hidden=hidden)


@on_action(router, *TOGGLES)
async def on_toggle(callback: CallbackQuery, callback_data: ActCB, store: ConfigStore, sysd: Systemd) -> None:
    project = await project_of(callback, callback_data.p)
    if project is None:
        return
    await callback.answer()
    key = TOGGLES[callback_data.a]

    async def after(target: Message, done: str) -> None:
        await show_params(target, True, project, done)

    await save(message_of(callback), True, project, lambda p: store.update(p, lambda cfg: configstore.toggle_global(cfg, key)),
               after, NavCB(s="par", p=project.key), sysd)


@on_action(router, *VALUES)
async def on_value(callback: CallbackQuery, callback_data: ActCB, state: FSMContext) -> None:
    project = await project_of(callback, callback_data.p)
    if project is None:
        return
    key = VALUES[callback_data.a]
    current = value_text(status.project_info(project).data, key)
    await start_form(callback, state, Input.value,
                     f"{head(title(callback_data.a))} — сейчас: {current}.\n\n{ASKS[key]}",
                     NavCB(s="par", p=project.key), data={"kind": "global", "p": project.key, "key": key})


@input_kind("global")
async def set_value(message: Message, state: FSMContext, raw: str, data: dict, store: ConfigStore,
                    sysd: Systemd, **_) -> None:
    key = data["key"]
    value: Any
    try:
        if raw == configstore.CLEAR:
            value = None
        elif key in ("tech_channel", "broadcast_channel"):
            value = configstore.parse_channel_id(raw)
        elif key == "broadcast_targets":
            value = [configstore.yaml_ref(r) for r in configstore.parse_chat_refs(raw)]
        else:
            value = configstore.parse_url(raw)
    except ConfigError as e:
        await message.answer(f"{texts.config_error(e.code, e.detail)}\nПришлите ещё раз:")
        return
    project = status.find(data["p"])
    await leave_form(message.chat.id, state)
    if project is None:
        await message.answer(texts.NO_PROJECT)
        return

    async def after(target: Message, done: str) -> None:
        await show_params(target, True, project, done)

    await save(message, False, project, lambda p: store.update(p, lambda cfg: configstore.set_global_value(cfg, key, value)),
               after, NavCB(s="par", p=project.key), sysd)
