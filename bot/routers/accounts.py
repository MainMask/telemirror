"""👤 Аккаунты: the Telegram sessions (``sessions/*.jsession``) the mirrors run
on — the list, a card, a sign-in by phone, an uploaded .jsession. A new or
changed session can go straight to a project (FSM data ``then``: "new" — the
project being created, "<key>" — that project's account, "" — just the list).
"""

import asyncio
import logging
import os
import re
from typing import Optional

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from telethon import errors

from bot import pending, settings, status, texts
from bot.callbacks import ChoiceCB, NavCB
from bot.keyboards.common import button, choice_kb, paged_rows, pages
from bot.registry import ROW_ACCOUNT, SCREENS, TITLES, YES_DELETE, title
from bot.routers._common import (
    ask,
    ask_confirm,
    confirmed,
    delete_quietly,
    end_form,
    message_of,
    on_action,
    stale_tap,
    start_form,
)
from bot.screens import open_screen, show, view
from bot.sessions import account_label, account_of, session_files, users_of
from bot.states import Input, Login, NewProject, UploadSession, leave_form
from bot.texts import esc, head, project_label
from telemirror import projects
from telemirror.misc import session_import
from telemirror.misc.jsession import TDESKTOP_APP, load_jsession, save_jsession
from telemirror.misc.telegram_client import new_tdesktop_client

logger = logging.getLogger(__name__)
router = Router(name="accounts")

LOGIN_STALE = "Вход устарел — начните заново."


def too_many(seconds: int) -> str:
    return f"⚠️ Слишком много попыток, подождите {seconds} с."


# ── 👤 Аккаунты / 👤 Аккаунт ────────────────────────────────────────────────


@view("acc")
async def accounts_view(message: Message, edit: bool, nav: NavCB, *, note: str = "", **_) -> None:
    paths = session_files()
    page = nav.pg % pages(len(paths), settings.PAGE_SIZE)
    items = []
    for n, path in enumerate(paths):
        used = len(users_of(path))
        items.append(button(f"{ROW_ACCOUNT} {account_label(path)} · проектов: {used}", NavCB(s="acct", i=n, pg=page)))
    body = ("Аккаунтов пока нет. От имени аккаунта Telegram зеркало читает каналы-источники и "
            "публикует в ваших каналах. Войдите по номеру или загрузите файл входа.") if not paths else (
        f"Аккаунтов: <b>{len(paths)}</b>."
    )
    more = "Проекты с одним аккаунтом работают по очереди, с разными — одновременно." if paths else ""
    own = paged_rows(items, page, settings.PAGE_SIZE, lambda pg: NavCB(s="acc", pg=pg))
    await show(message, edit, "acc", body=body, more=more, note=note, own=own, pg=page)


@view("acct")
async def account_view(message: Message, edit: bool, nav: NavCB, *, note: str = "", **_) -> None:
    paths = session_files()
    if not 0 <= nav.i < len(paths):
        await show(message, edit, "acc", note=texts.STALE_BUTTON)
        return
    path = paths[nav.i]
    acc, used = account_of(path), users_of(path)
    try:
        app = load_jsession(str(projects.REPO_DIR / path)).get("application") or {}
    except (OSError, ValueError) as e:
        app = {}
        note = note or f"⚠️ Файл не читается: <code>{esc(e)}</code>"
    name = " ".join(filter(None, (acc.get("first_name"), acc.get("last_name")))) or texts.UNKNOWN
    body = "\n".join([
        f"👤 <b>{esc(account_label(path))}</b>",
        f"Имя: {esc(name)}",
        "Проекты: " + (", ".join(esc(project_label(p)) for p in used) or "нет")
        + ("" if not used else " — пока аккаунт в них, удалить его нельзя"),
    ])
    more = (f"Технические подробности: файл <code>{esc(path)}</code>; вход как "
            f"{esc(app.get('device_name') or texts.UNKNOWN)}, {esc(app.get('app_version') or texts.UNKNOWN)} "
            f"(api_id {esc(app.get('api_id') or texts.UNKNOWN)}).")
    await show(message, edit, "acct", body=body, more=more, note=note, i=nav.i, pg=nav.pg,
               hidden=("acc_del",) if used else ())


@on_action(router, "acc_del")
async def on_delete(callback: CallbackQuery, callback_data, state: FSMContext) -> None:
    paths = session_files()
    if not 0 <= callback_data.i < len(paths) or users_of(paths[callback_data.i]):
        await stale_tap(callback)
        return
    path = paths[callback_data.i]
    await ask_confirm(
        callback, state,
        f"{head(title('acc_del'))} сессию {esc(account_label(path))}?\n\n"
        "Файл удаляется с сервера. Сам вход в аккаунт остаётся активным — завершите его "
        "в Telegram: Настройки → Устройства.",
        "acc_del", NavCB(s="acct", i=callback_data.i, pg=callback_data.pg), yes=YES_DELETE, path=path,
    )


@confirmed("acc_del")
async def do_delete(callback: CallbackQuery, action: dict, deps: dict, **_) -> None:
    path = action["path"]
    if users_of(path):
        await stale_tap(callback)
        return
    for target in (projects.REPO_DIR / path, projects.REPO_DIR / f"{path}.lock"):
        target.unlink(missing_ok=True)
    await callback.answer()
    await open_screen(NavCB(s="acc"), message_of(callback), True, deps, note=f"✅ Сессия {esc(path)} удалена.")


# ── where a new session goes (then) ─────────────────────────────────────────


async def session_ready(message: Message, state: FSMContext, path: str, note: str, deps: dict) -> None:
    """A session was saved or picked: give it to whoever asked (FSM data
    ``then``) — the project being created, a project's 👤 Аккаунт, the list."""
    data = await state.get_data()
    then = data.get("then", "")
    await leave_form(message.chat.id, state)
    note = f"{note}\n" if note else ""
    if then == "new":
        project = projects.create_project(data["name"], data["icon"], path)
        logger.info("panel: project %s created on %s", project.key, path)
        await open_screen(NavCB(s="card", p=project.key), message, False, deps, note=(
            f"{note}✅ Проект {esc(project_label(project))} создан. Теперь добавьте направления: "
            f"{SCREENS['dirs'].title} → {title('dir_add')}."))
    elif then:
        if status.find(then) is not None:  # else open_screen says it's gone
            projects.update_project(then, session=path)
            note += f"✅ Аккаунт проекта: {esc(account_label(path))}. Перезапустите зеркало, чтобы он заработал."
        await open_screen(NavCB(s="mng", p=then), message, False, deps, note=note)
    else:
        await open_screen(NavCB(s="acc"), message, False, deps, note=note.strip())


# ── 📤 Загрузить сессию ─────────────────────────────────────────────────────

UPLOAD_ASK = (
    f"{head(title('acc_upload'))} — пришлите документом один из вариантов:\n\n"
    "• ZIP с папкой <code>tdata</code> из Telegram Desktop;\n"
    "• файл <code>.session</code> (Telethon) вместе с <code>.json</code> того же имени — выделите оба "
    "и отправьте вместе — или ZIP с ними;\n"
    "• файл <code>.jsession</code>.\n\n"
    "В этом аккаунте уже должен быть выполнен вход. Бот проверит это, подключившись к аккаунту, и сохранит "
    "файл на сервере.\n\n"
    "<i>Облачный пароль не нужен и не сохраняется. Присланные файлы бот удалит из чата.</i>"
)
UPLOAD_SUFFIXES = (".zip", ".session", ".json", ".jsession")


@on_action(router, "acc_upload")
async def on_upload(callback: CallbackQuery, state: FSMContext) -> None:
    await start_form(callback, state, UploadSession.file, UPLOAD_ASK, NavCB(s="acc"), data={"then": ""})


@router.message(UploadSession.file)
async def on_upload_file(message: Message, state: FSMContext, bot: Bot, deps: dict, album=None) -> None:
    files, skipped = {}, []
    for item in album or [message]:
        doc = item.document
        name = os.path.basename(doc.file_name or "") if doc else ""
        if doc is None or not name.lower().endswith(UPLOAD_SUFFIXES):
            skipped.append(name or "не файл")
            continue
        if (doc.file_size or 0) > settings.UPLOAD_MAX_BYTES:
            skipped.append(f"{name} — больше {settings.UPLOAD_MAX_BYTES // 2**20} МБ")
        else:
            raw = await bot.download(doc)
            files[name] = raw.read() if raw else b""
        await delete_quietly(item)  # a session in the chat history = access to the account
    if skipped:
        await message.answer("Не принято: " + ", ".join(esc(x) for x in skipped)
                             + ". Нужны .zip, .session, .json или .jsession."
                             + ("" if files else " Пришлите файл — или /cancel, чтобы выйти."))
    if not files:
        if not skipped:
            await message.answer(f"Нужен файл-документ. {texts.SEND_AGAIN}")
        return
    jsessions = [n for n in files if n.lower().endswith(".jsession")]
    if jsessions and len(files) > 1:
        await message.answer(f"Файл .jsession присылайте отдельно, по одному. {texts.SEND_AGAIN}")
        return
    if jsessions and len(files[jsessions[0]]) > settings.JSESSION_MAX_BYTES:
        await message.answer("Файл слишком большой для сессии. Пришлите .jsession ещё раз:")
        return
    await _import(message, state, files, None, deps)


async def _import(message: Message, state: FSMContext, files: dict, passcode: Optional[str],
                  deps: dict) -> None:
    """tdata / .session (+ .json) / .jsession: checked by connecting, saved as a .jsession."""
    await message.answer("⏳ Проверяю сессию: подключаюсь к аккаунту…")
    try:
        saved = await session_import.import_files(files, projects.SESSIONS_DIR, passcode)
    except session_import.NeedPasscode as e:
        await pending.put(message.chat.id, pending.Upload(files))  # too big for FSM data
        await ask(message, state, UploadSession.passcode,
                  f"🔐 {esc(e)}.\n\nПришлите код-пароль, которым защищён Telegram Desktop, — тот, что "
                  "вводится при запуске программы.\n\n<i>Сообщение бот удалит, код-пароль не сохраняется.</i>")
        return
    except session_import.SessionImportError as e:
        await ask(message, state, UploadSession.file, f"⚠️ Не загружено: {esc(e)}. Пришлите другие файлы:")
        return
    path = os.path.relpath(saved, projects.REPO_DIR)
    logger.info("panel: session %s imported", path)
    await session_ready(message, state, path, f"✅ Сессия {esc(account_label(path))} сохранена.", deps)


@router.message(UploadSession.passcode)
async def on_passcode(message: Message, state: FSMContext, deps: dict) -> None:
    passcode = message.text or ""
    await delete_quietly(message)
    upload = pending.get(message.chat.id, pending.Upload)
    if upload is None:
        await end_form(message, state, "Файлы потерялись — начните заново.")
        return
    if not passcode:
        await message.answer(f"Нужен код-пароль текстом. {texts.SEND_AGAIN}")
        return
    await _import(message, state, upload.files, passcode, deps)


# ── 🔑 Войти по номеру ──────────────────────────────────────────────────────

PHONE_ASK = (
    f"{head(title('acc_login'))} — какой номер у аккаунта?\n\n"
    "Пришлите его в международном формате, например <code>+79991234567</code>.\n\n"
    "<i>Бот войдёт в аккаунт как приложение Telegram Desktop — этот вход появится в списке устройств.</i>"
)
CODE_ASK = (
    "Пришлите код из Telegram <b>через пробелы</b>, например <code>1 2 3 4 5</code>. Код, отправленный "
    "слитно, Telegram аннулирует.\n\n"
    "<i>Сообщение с кодом бот сразу удалит.</i>"
)


def resend_kb():
    return choice_kb("login_resend", [(TITLES["resend"], "resend")])


async def _timed(request):
    """One Telegram request of the sign-in, bounded: a hung one ends as
    "Telegram не ответил" (TimeoutError's text is empty)."""
    return await asyncio.wait_for(request, settings.LOGIN_TIMEOUT_SEC)


def normalize_phone(raw: str) -> Optional[str]:
    digits = re.sub(r"[\s()+-]", "", raw or "")
    return digits if digits.isdigit() and 10 <= len(digits) <= 15 else None


def code_digits(raw: str) -> Optional[str]:
    digits = re.sub(r"\D", "", raw or "")
    return digits if 4 <= len(digits) <= 8 else None


@on_action(router, "acc_login")
async def on_login(callback: CallbackQuery, state: FSMContext) -> None:
    await start_form(callback, state, Login.phone, PHONE_ASK, NavCB(s="acc"), data={"then": ""})


@router.message(Login.phone)
async def on_phone(message: Message, state: FSMContext) -> None:
    phone = normalize_phone(message.text or "")
    if phone is None:
        await message.answer("Не похоже на номер. Пришлите его в формате +79991234567:")
        return
    await pending.close(message.chat.id)
    client = new_tdesktop_client()
    try:
        await _timed(client.connect())
        sent = await _timed(client.send_code_request(f"+{phone}"))
    except errors.FloodWaitError as e:
        await client.disconnect()
        await end_form(message, state, too_many(e.seconds))
        return
    except Exception as e:  # noqa: BLE001 - shown to the admin, the form ends
        await client.disconnect()
        await end_form(message, state, f"⚠️ Код не отправлен: {esc(e) or 'Telegram не ответил'}.")
        return
    await pending.put(message.chat.id, pending.Login(client, phone, sent.phone_code_hash))
    await ask(message, state, Login.code, f"📲 Код отправлен.\n{CODE_ASK}", resend_kb())


@router.callback_query(Login.code, ChoiceCB.filter(F.scope == "login_resend"))
async def on_resend(callback: CallbackQuery, state: FSMContext) -> None:
    login = pending.get(callback.from_user.id, pending.Login)
    if login is None:
        await stale_tap(callback, LOGIN_STALE)
        return
    await callback.answer()
    try:
        sent = await _timed(login.client.send_code_request(f"+{login.phone}"))
    except errors.FloodWaitError as e:
        await message_of(callback).answer(too_many(e.seconds))
        return
    except Exception as e:  # noqa: BLE001 - the step stays: the old code may still work
        await message_of(callback).answer(f"⚠️ Код не отправлен: {esc(e) or 'Telegram не ответил'}.")
        return
    login.phone_code_hash = sent.phone_code_hash
    await message_of(callback).edit_reply_markup(reply_markup=None)  # the old prompt's button is spent
    await ask(message_of(callback), state, Login.code, f"📲 Новый код отправлен.\n{CODE_ASK}", resend_kb())


@router.message(Login.code)
async def on_code(message: Message, state: FSMContext, deps: dict) -> None:
    login = pending.get(message.chat.id, pending.Login)
    code = code_digits(message.text or "")
    await delete_quietly(message)
    if login is None:
        await end_form(message, state, LOGIN_STALE)
        return
    if code is None:
        await message.answer(CODE_ASK)
        return
    try:
        await _timed(login.client.sign_in(f"+{login.phone}", code, phone_code_hash=login.phone_code_hash))
    except errors.SessionPasswordNeededError:
        await ask(message, state, Login.password,
                  "🔐 У аккаунта включён облачный пароль (двухэтапная проверка). Пришлите его.\n\n"
                  "<i>Сообщение бот удалит, пароль нигде не сохраняется.</i>")
        return
    except errors.PhoneCodeInvalidError:
        await message.answer(f"Неверный код. {CODE_ASK}")
        return
    except errors.PhoneCodeExpiredError:
        await ask(message, state, Login.code,
                  "⌛ Код больше не действует: истёк или Telegram аннулировал его, увидев слитно.\n\n"
                  f"Нажмите {head(TITLES['resend'])} и пришлите новый код через пробелы.", resend_kb())
        return
    except errors.FloodWaitError as e:
        await message.answer(f"{too_many(e.seconds)} Затем пришлите код снова.")
        return
    except Exception as e:  # noqa: BLE001 - the form ends (end_form drops the client)
        await end_form(message, state, f"⚠️ Вход не удался: {esc(e) or 'Telegram не ответил'}")
        return
    await _finish(message, state, login, deps)


@router.message(Login.password)
async def on_password(message: Message, state: FSMContext, deps: dict) -> None:
    login = pending.get(message.chat.id, pending.Login)
    password = message.text or ""
    await delete_quietly(message)
    if login is None:
        await end_form(message, state, LOGIN_STALE)
        return
    if not password:
        await message.answer(f"Нужен пароль текстом. {texts.SEND_AGAIN}")
        return
    try:
        await _timed(login.client.sign_in(password=password))
    except errors.PasswordHashInvalidError:
        await message.answer(f"Неверный пароль. {texts.SEND_AGAIN}")
        return
    except errors.FloodWaitError as e:
        await message.answer(f"{too_many(e.seconds)} Затем пришлите пароль снова.")
        return
    except Exception as e:  # noqa: BLE001 - the form ends (end_form drops the client)
        await end_form(message, state, f"⚠️ Вход не удался: {esc(e) or 'Telegram не ответил'}")
        return
    await _finish(message, state, login, deps)


async def _finish(message: Message, state: FSMContext, login: pending.Login, deps: dict) -> None:
    """Signed in: save the session (an old file of this number is kept as .bak)."""
    try:
        me = await login.client.get_me()
        path = f"sessions/{me.phone or login.phone}.jsession"
        save_jsession(str(projects.REPO_DIR / path), login.client.session.save(), me, TDESKTOP_APP)
    except Exception as e:  # noqa: BLE001 - the form ends (end_form drops the client)
        await end_form(message, state, f"⚠️ Аккаунт не сохранён: {esc(e)}")
        return
    logger.info("panel: signed in %s", path)
    await session_ready(message, state, path, f"✅ Вход выполнен: {esc(account_label(path))}.", deps)


@router.callback_query(StateFilter(NewProject.account, Input.value), ChoiceCB.filter(F.scope == "acc_pick"))
async def on_pick(callback: CallbackQuery, callback_data: ChoiceCB, state: FSMContext, deps: dict) -> None:
    """An account picker (a new project's, a project's 👤 Аккаунт): a session,
    or on to a new one — 🔑 / 📤 — with the form's data (and its ✖️ origin) kept."""
    data = await state.get_data()
    if "accounts" not in data:
        await stale_tap(callback)
        return
    if callback_data.value in ("login", "upload"):
        await callback.answer()
        step, prompt = (Login.phone, PHONE_ASK) if callback_data.value == "login" else (UploadSession.file, UPLOAD_ASK)
        await message_of(callback).edit_reply_markup(reply_markup=None)
        await ask(message_of(callback), state, step, prompt)
        return
    paths = data["accounts"]
    index = int(callback_data.value) if callback_data.value.isdigit() else -1
    if not 0 <= index < len(paths):
        await stale_tap(callback)
        return
    await callback.answer()
    await message_of(callback).edit_reply_markup(reply_markup=None)
    await session_ready(message_of(callback), state, paths[index], "", deps)
