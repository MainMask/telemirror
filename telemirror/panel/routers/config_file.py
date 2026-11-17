"""🗂 Конфиг: the project's mirror config file — download, replace with an
uploaded one, roll back to the copy taken before the last change."""

from typing import Any

import yaml as pyyaml
from aiogram import Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from telemirror.panel import configstore, status, texts
from telemirror.panel.callbacks import ActCB, NavCB
from telemirror.panel.configstore import ConfigError, ConfigStore
from telemirror.panel.registry import title
from telemirror.panel.routers._common import (
    ask_confirm,
    confirmed,
    message_of,
    on_action,
    project_of,
    stale_tap,
    start_form,
)
from telemirror.panel.screens import esc, head, show, view
from telemirror.panel.states import UploadConfig
from telemirror.panel.systemd import Systemd
from telemirror.panel.writes import save
from telemirror.projects import Project

router = Router(name="config_file")


def _count(text: str) -> Any:
    try:
        return len((pyyaml.safe_load(text) or {}).get("directions") or [])
    except Exception:  # noqa: BLE001 - a broken file is shown as "—"
        return texts.UNKNOWN


def diff_block(old: str, new: str) -> str:
    diff, truncated = configstore.text_diff(old, new)
    if not diff:
        return texts.DIFF_SAME
    return texts.DIFF_TITLE.format(diff=esc(diff) + (texts.DIFF_TRUNCATED if truncated else ""))


@view("cfg")
async def config_view(message: Message, edit: bool, nav: NavCB, state: FSMContext, note: str = "", **_) -> None:
    project = status.find(nav.p)
    if project is None:
        await message.answer(texts.NO_PROJECT)
        return
    await show_config(message, edit, project, note)


async def show_config(message: Message, edit: bool, project: Project, note: str = "") -> None:
    path = project.config_path
    lines = [f"Файл: <code>{esc(project.config)}</code>"]
    if path.exists():
        lines.append(f"Изменён: {texts.fmt_ts(path.stat().st_mtime)} · направлений: "
                     f"<b>{_count(path.read_text(encoding='utf-8'))}</b>")
    else:
        lines.append(texts.READ_ONLY["missing"])
    backup = configstore.backup_info(project)
    lines.append(
        f"Резервная копия: от {texts.fmt_ts(backup.mtime)}, направлений: "
        f"<b>{texts.UNKNOWN if backup.directions is None else backup.directions}</b>"
        if backup else "Резервной копии нет — она появится при первом изменении из панели."
    )
    hidden = [] if path.exists() else ["cfg_get", "cfg_put"]
    if backup is None:
        hidden.append("cfg_undo")
    await show(message, edit, "cfg", project, body="\n".join(lines), note=note, hidden=tuple(hidden))


@on_action(router, "cfg_get")
async def on_download(callback: CallbackQuery, callback_data: ActCB, bot: Bot) -> None:
    project = await project_of(callback, callback_data.p)
    if project is None:
        return
    path = project.config_path
    if not path.exists() or path.stat().st_size == 0:
        await stale_tap(callback, texts.READ_ONLY["missing"])
        return
    await callback.answer()
    await bot.send_document(
        callback.from_user.id, BufferedInputFile(path.read_bytes(), filename=path.name),
        caption=f"📥 {esc(project.icon)} {esc(project.name)}: {esc(path.name)} — текущая версия.",
    )


@on_action(router, "cfg_put")
async def on_upload(callback: CallbackQuery, callback_data: ActCB, state: FSMContext) -> None:
    project = await project_of(callback, callback_data.p)
    if project is None:
        return
    await start_form(
        callback, state, UploadConfig.file,
        f"{head(title('cfg_put'))} — пришлите YAML-файл документом (до "
        f"{configstore.MAX_UPLOAD_BYTES // 1024} КБ). Перед заменой он проверяется тем же загрузчиком, "
        "что и при старте сервиса; текущий файл станет резервной копией.",
        NavCB(s="cfg", p=project.key), data={"p": project.key},
    )


@router.message(UploadConfig.file)
async def on_upload_file(message: Message, state: FSMContext, bot: Bot) -> None:
    doc = message.document
    if doc is None:
        await message.answer("Нужен файл-документ с конфигурацией (.yml). Пришлите ещё раз:")
        return
    project = status.find((await state.get_data()).get("p", ""))
    if project is None:
        await message.answer(texts.NO_PROJECT)
        return
    try:
        if (doc.file_size or 0) > configstore.MAX_UPLOAD_BYTES:
            raise ConfigError("too_big", f"{configstore.MAX_UPLOAD_BYTES // 1024} KB")
        buf = await bot.download(doc)
        try:
            text = (buf.read() if buf is not None else b"").decode("utf-8")
        except UnicodeDecodeError:
            raise ConfigError("bad_yaml", "not UTF-8 text") from None
        configstore.check_yaml(text)
    except ConfigError as e:
        await message.answer(f"{texts.config_error(e.code, e.detail)}\nПришлите другой файл:")
        return
    # The raw text, not configstore.load(): upload must also work when the
    # current file is broken and doesn't parse.
    current = project.config_path.read_text(encoding="utf-8") if project.config_path.exists() else ""
    await ask_confirm(
        message, state,
        f"{head(title('cfg_put'))}: заменить конфигурацию файлом <code>{esc(doc.file_name or 'config.yml')}</code>?\n\n"
        f"Направлений: <b>{_count(text)}</b> (сейчас: <b>{_count(current)}</b>). Текущий файл станет "
        f"резервной копией.\n\n{diff_block(current, text)}",
        "cfg_put", NavCB(s="cfg", p=project.key), p=project.key, upload=text, sha=configstore.sha(current),
    )


@confirmed("cfg_put")
async def do_upload(callback: CallbackQuery, action: dict, state: FSMContext, store: ConfigStore,
                    sysd: Systemd, **_) -> None:
    project = await project_of(callback, action["p"])
    if project is None:
        return
    await callback.answer()

    async def after(target: Message, done: str) -> None:
        await show_config(target, True, project, "✅ Конфигурация заменена. " + done.removeprefix("✅ Сохранено. "))

    await save(message_of(callback), True, project, lambda p: store.replace_text(p, action["upload"], action["sha"]),
               after, NavCB(s="cfg", p=project.key), sysd)


@on_action(router, "cfg_undo")
async def on_rollback(callback: CallbackQuery, callback_data: ActCB, state: FSMContext) -> None:
    project = await project_of(callback, callback_data.p)
    if project is None:
        return
    backup = configstore.backup_info(project)
    if backup is None:
        await stale_tap(callback, texts.config_error("no_backup"))
        return
    current = project.config_path.read_text(encoding="utf-8") if project.config_path.exists() else ""
    await ask_confirm(
        callback, state,
        f"{head(title('cfg_undo'))} к копии от {texts.fmt_ts(backup.mtime)}?\n\nНаправлений в ней: "
        f"<b>{texts.UNKNOWN if backup.directions is None else backup.directions}</b> (сейчас: "
        f"<b>{_count(current)}</b>). Текущий файл сам станет копией — откат можно отменить повторным "
        f"откатом.\n\n{diff_block(current, configstore.backup_path(project).read_text(encoding='utf-8'))}",
        "cfg_undo", NavCB(s="cfg", p=project.key), p=project.key,
    )


@confirmed("cfg_undo")
async def do_rollback(callback: CallbackQuery, action: dict, state: FSMContext, store: ConfigStore,
                      sysd: Systemd, **_) -> None:
    project = await project_of(callback, action["p"])
    if project is None:
        return
    await callback.answer()

    async def after(target: Message, done: str) -> None:
        await show_config(target, True, project, "✅ Откат выполнен. " + done.removeprefix("✅ Сохранено. "))

    await save(message_of(callback), True, project, store.restore_backup, after, NavCB(s="cfg", p=project.key), sysd)
