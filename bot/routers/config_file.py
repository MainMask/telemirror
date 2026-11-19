"""💾 Файл настроек: the project's mirror config file — download, replace with an
uploaded one, roll back to the copy taken before the last change."""

from typing import Any

import yaml as pyyaml
from aiogram import Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot import configstore, settings, texts
from bot.callbacks import NavCB
from bot.configparse import ConfigError
from bot.configstore import ConfigStore
from bot.registry import title
from bot.routers._common import (
    ask_confirm,
    confirmed,
    message_of,
    on_action,
    project_of,
    retry,
    stale_tap,
    start_form,
)
from bot.screens import show, view
from bot.states import UploadConfig
from bot.texts import esc, head
from bot.writes import save
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


def _config(project: Project) -> NavCB:
    return NavCB(s="cfg", p=project.key)


@view("cfg")
async def config_view(message: Message, edit: bool, nav: NavCB, *, project: Project, note: str = "",
                      **_) -> None:
    path = project.config_path
    lines = [f"Файл: <code>{esc(project.config)}</code>"]
    if path.exists():
        lines.append(f"Изменён: {texts.fmt_ts(path.stat().st_mtime)} · направлений: "
                     f"<b>{_count(path.read_text(encoding='utf-8'))}</b>")
    else:
        lines.append(texts.CONFIG_MISSING)
    backup = configstore.backup_info(project)
    lines.append(
        f"Прошлая версия: от {texts.fmt_ts(backup.mtime)}, направлений: "
        f"<b>{texts.UNKNOWN if backup.directions is None else backup.directions}</b>"
        if backup else "Прошлой версии нет — она появится при первом изменении из панели."
    )
    hidden = [] if path.exists() else ["cfg_get", "cfg_put"]
    if backup is None:
        hidden.append("cfg_undo")
    more = "Все настройки проекта одним файлом — для тех, кто хочет править их вручную. Обычно хватает меню."
    await show(message, edit, "cfg", project, body="\n".join(lines), more=more, note=note, hidden=tuple(hidden),
               pg=nav.pg)


@on_action(router, "cfg_get")
async def on_download(callback: CallbackQuery, project: Project, bot: Bot) -> None:
    path = project.config_path
    if not path.exists() or path.stat().st_size == 0:
        await stale_tap(callback, texts.CONFIG_MISSING)
        return
    await callback.answer()
    await bot.send_document(
        callback.from_user.id, BufferedInputFile(path.read_bytes(), filename=path.name),
        caption=f"📥 {esc(texts.project_label(project))}: {esc(path.name)} — текущая версия.",
    )


@on_action(router, "cfg_put")
async def on_upload(callback: CallbackQuery, project: Project, state: FSMContext) -> None:
    await start_form(
        callback, state, UploadConfig.file,
        f"{head(title('cfg_put'))} — пришлите YAML-файл документом (до "
        f"{settings.CONFIG_MAX_BYTES // 1024} КБ). Перед заменой он будет проверен; текущий файл "
        "сохранится как прошлая версия.",
        _config(project), data={"p": project.key},
    )


@router.message(UploadConfig.file)
async def on_upload_file(message: Message, state: FSMContext, bot: Bot) -> None:
    doc = message.document
    if doc is None:
        await message.answer(f"Нужен файл настроек (.yml), отправленный как документ. {texts.SEND_AGAIN}")
        return
    if (project := await project_of(message, (await state.get_data()).get("p", ""))) is None:
        return
    try:
        if (doc.file_size or 0) > settings.CONFIG_MAX_BYTES:
            raise ConfigError("too_big", f"{settings.CONFIG_MAX_BYTES // 1024} KB")
        buf = await bot.download(doc)
        try:
            text = (buf.read() if buf is not None else b"").decode("utf-8")
        except UnicodeDecodeError:
            raise ConfigError("bad_yaml", "not UTF-8 text") from None
        configstore.check_yaml(text)
    except ConfigError as e:
        await retry(message, e)
        return
    # The raw text, not configstore.load(): upload must also work when the
    # current file is broken and doesn't parse.
    current = project.config_path.read_text(encoding="utf-8") if project.config_path.exists() else ""
    await ask_confirm(
        message, state,
        f"{head(title('cfg_put'))}: заменить настройки файлом <code>{esc(doc.file_name or 'config.yml')}</code>?\n\n"
        f"Направлений: <b>{_count(text)}</b> (сейчас: <b>{_count(current)}</b>). Текущий файл сохранится "
        f"как прошлая версия.\n\n{diff_block(current, text)}",
        "cfg_put", _config(project), p=project.key, upload=text, sha=configstore.sha(current),
    )


def _replaced(what: str):
    return lambda done: f"✅ {what}. " + done.removeprefix("✅ Сохранено. ")


@confirmed("cfg_put")
async def do_upload(callback: CallbackQuery, action: dict, project: Project, store: ConfigStore, deps: dict,
                    **_) -> None:
    await callback.answer()
    await save(message_of(callback), True, project, lambda p: store.replace_text(p, action["upload"], action["sha"]),
               _config(project), deps, outcome=_replaced("Настройки заменены"))


@on_action(router, "cfg_undo")
async def on_rollback(callback: CallbackQuery, project: Project, state: FSMContext) -> None:
    backup = configstore.backup_info(project)
    if backup is None:
        await stale_tap(callback, texts.config_error("no_backup"))
        return
    current = project.config_path.read_text(encoding="utf-8") if project.config_path.exists() else ""
    await ask_confirm(
        callback, state,
        f"{head(title('cfg_undo'))} к версии от {texts.fmt_ts(backup.mtime)}?\n\nНаправлений в ней: "
        f"<b>{texts.UNKNOWN if backup.directions is None else backup.directions}</b> (сейчас: "
        f"<b>{_count(current)}</b>). Текущие настройки сохранятся как прошлая версия — передумаете, "
        f"нажмите ещё раз.\n\n{diff_block(current, configstore.backup_path(project).read_text(encoding='utf-8'))}",
        "cfg_undo", _config(project), p=project.key,
    )


@confirmed("cfg_undo")
async def do_rollback(callback: CallbackQuery, action: dict, project: Project, store: ConfigStore, deps: dict,
                      **_) -> None:
    await callback.answer()
    await save(message_of(callback), True, project, store.restore_backup, _config(project), deps,
               outcome=_replaced("Откат выполнен"))
