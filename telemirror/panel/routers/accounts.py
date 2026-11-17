"""👤 Аккаунты: the Telegram sessions (``sessions/*.jsession``) the mirrors run
on — the list, a card, a sign-in by phone, an uploaded .jsession. A new or
changed session can go straight to a project (FSM data ``then``: "new" — the
project being created, "<key>" — that project's account, "" — just the list).
"""

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Optional

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from telethon import errors
from telethon.sessions import StringSession

from telemirror import projects
from telemirror.misc import session_import
from telemirror.misc.jsession import TDESKTOP_APP, load_jsession, save_jsession
from telemirror.misc.telegram_client import apply_lang_pack
from telemirror.panel import logins, settings, texts
from telemirror.panel.callbacks import ChoiceCB, NavCB
from telemirror.panel.keyboards.common import button, choice_kb, pages, paged_rows
from telemirror.panel.registry import YES_DELETE, title
from telemirror.panel.routers._common import (
    ask,
    ask_confirm,
    confirmed,
    delete_quietly,
    end_form,
    leave_form,
    message_of,
    on_action,
    stale_tap,
    start_form,
)
from telemirror.panel.screens import esc, head, show, view
from telemirror.panel.states import Login, UploadSession
from telemirror.panel.systemd import Systemd

logger = logging.getLogger(__name__)
router = Router(name="accounts")

MAX_SESSION_BYTES = 64 * 1024


# ── the sessions ────────────────────────────────────────────────────────────


def session_files() -> list:
    """``sessions/*.jsession`` as repo-relative paths, sorted."""
    folder = projects.SESSIONS_DIR
    files = sorted(folder.glob("*.jsession")) if folder.is_dir() else []
    return [os.path.relpath(f, projects.REPO_DIR) for f in files]


def account_of(path: str) -> dict:
    try:
        return load_jsession(str(projects.REPO_DIR / path)).get("account") or {}
    except (OSError, ValueError):
        return {}


def account_label(path: str) -> str:
    """``+79131332002 · @name`` (the file name if it has no account data)."""
    acc = account_of(path)
    phone = f"+{acc['phone_number']}" if acc.get("phone_number") else Path(path).stem
    return f"{phone} · @{acc['username']}" if acc.get("username") else phone


def users_of(path: str) -> list:
    """The projects on this session."""
    mine = (projects.REPO_DIR / path).resolve()
    return [p for p in projects.list_projects() if p.session_path.resolve() == mine]


def account_choices(paths: list) -> list:
    """(label, value) of an account picker: the sessions by index, then a new one."""
    return [
        *((f"👤 {account_label(p)}", str(n)) for n, p in enumerate(paths)),
        (title("acc_login"), "login"),
        (title("acc_upload"), "upload"),
    ]


# ── 👤 Аккаунты / 👤 Аккаунт ────────────────────────────────────────────────


@view("acc")
async def accounts_view(message: Message, edit: bool, nav: NavCB, state: FSMContext, note: str = "", **_) -> None:
    paths = session_files()
    items = []
    for n, path in enumerate(paths):
        used = len(users_of(path))
        items.append(button(f"👤 {account_label(path)} · проектов: {used}", NavCB(s="acct", i=n, pg=nav.pg)))
    body = "Сессий пока нет — войдите по номеру или загрузите файл." if not paths else (
        f"Сессий: <b>{len(paths)}</b>. Одна сессия = один вход в аккаунт: проекты на одной "
        "сессии работают по очереди, на разных — одновременно."
    )
    own = paged_rows(items, nav.pg, settings.PAGE_SIZE, lambda pg: NavCB(s="acc", pg=pg))
    await show(message, edit, "acc", body=body, note=note, own=own, pg=nav.pg % pages(len(items), settings.PAGE_SIZE))


@view("acct")
async def account_view(message: Message, edit: bool, nav: NavCB, state: FSMContext, note: str = "", **_) -> None:
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
        f"Файл: <code>{esc(path)}</code>",
        f"Приложение: {esc(app.get('device_name') or texts.UNKNOWN)}, {esc(app.get('app_version') or texts.UNKNOWN)} "
        f"(api_id {esc(app.get('api_id') or texts.UNKNOWN)})",
        "Проекты: " + (", ".join(esc(f"{p.icon} {p.name}") for p in used) or "нет"),
    ])
    await show(message, edit, "acct", body=body, note=note, i=nav.i, pg=nav.pg,
               hidden=("acc_del",) if used else (), back=NavCB(s="acc", pg=nav.pg))


@on_action(router, "acc_del")
async def on_delete(callback: CallbackQuery, callback_data, state: FSMContext) -> None:
    paths = session_files()
    if not 0 <= callback_data.i < len(paths) or users_of(paths[callback_data.i]):
        await stale_tap(callback)
        return
    path = paths[callback_data.i]
    await ask_confirm(
        callback, state,
        f"{head('🗑 Удалить сессию')} {esc(account_label(path))}?\n\n"
        "Файл удаляется с сервера. Сам вход в аккаунт остаётся активным — завершите его "
        "в Telegram: Настройки → Устройства.",
        "acc_del", NavCB(s="acct", i=callback_data.i), yes=YES_DELETE, path=path,
    )


@confirmed("acc_del")
async def do_delete(callback: CallbackQuery, action: dict, state: FSMContext, **deps) -> None:
    path = action["path"]
    if users_of(path):
        await stale_tap(callback)
        return
    for target in (projects.REPO_DIR / path, projects.REPO_DIR / f"{path}.lock"):
        target.unlink(missing_ok=True)
    await callback.answer()
    await accounts_view(message_of(callback), True, NavCB(s="acc"), state, note=f"✅ Сессия {esc(path)} удалена.")


# ── where a new session goes (then) ─────────────────────────────────────────


async def session_ready(message: Message, state: FSMContext, path: str, note: str, sysd: Systemd) -> None:
    """A session was saved: give it to whoever asked (FSM data ``then``)."""
    from telemirror.panel.routers import projects as project_screens

    data = await state.get_data()
    then = data.get("then", "")
    await leave_form(message.chat.id, state)
    if then == "new":
        await project_screens.create(message, data["name"], data["icon"], path, note, sysd)
    elif then:
        await project_screens.set_account(message, then, path, note)
    else:
        await accounts_view(message, False, NavCB(s="acc"), state, note=note)


async def ask_account(callback: CallbackQuery, state: FSMContext, value: str) -> bool:
    """A picker's 🔑 / 📤: on to the sign-in or the upload (the form's data kept).
    False for any other value."""
    if value == "login":
        await callback.answer()
        await ask(message_of(callback), state, Login.phone, PHONE_ASK)
        return True
    if value == "upload":
        await callback.answer()
        await ask(message_of(callback), state, UploadSession.file, UPLOAD_ASK)
        return True
    return False


# ── 📤 Загрузить сессию ─────────────────────────────────────────────────────

UPLOAD_ASK = (
    f"{head(title('acc_upload'))} — пришлите документом одно из:\n"
    "• ZIP с папкой <code>tdata</code> (Telegram Desktop);\n"
    "• файл <code>.session</code> (Telethon) вместе с <code>.json</code> того же имени — выделите оба "
    "и отправьте вместе, — или ZIP с ними;\n"
    "• файл <code>.jsession</code>.\n"
    "Аккаунт должен быть уже авторизован: бот проверит это, подключившись к нему, и сохранит сессию в "
    "<code>sessions/</code> на сервере. Пароль 2FA не нужен и не сохраняется. Файлы из чата я удалю."
)
UPLOAD_SUFFIXES = (".zip", ".session", ".json", ".jsession")
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # what the Bot API lets a bot download


@on_action(router, "acc_upload")
async def on_upload(callback: CallbackQuery, state: FSMContext) -> None:
    await start_form(callback, state, UploadSession.file, UPLOAD_ASK, NavCB(s="acc"), data={"then": ""})


@router.message(UploadSession.file)
async def on_upload_file(message: Message, state: FSMContext, bot: Bot, sysd: Systemd, album=None) -> None:
    files, skipped = {}, []
    for item in album or [message]:
        doc = item.document
        name = os.path.basename(doc.file_name or "") if doc else ""
        if doc is None or not name.lower().endswith(UPLOAD_SUFFIXES):
            skipped.append(name or "не файл")
            continue
        if (doc.file_size or 0) > MAX_UPLOAD_BYTES:
            skipped.append(f"{name} — больше {MAX_UPLOAD_BYTES // 2**20} МБ")
        else:
            raw = await bot.download(doc)
            files[name] = raw.read() if raw else b""
        await delete_quietly(item)  # a session in the chat history = access to the account
    if skipped:
        await message.answer("Не принято: " + ", ".join(esc(x) for x in skipped)
                             + ". Нужны .zip, .session, .json или .jsession.")
    if not files:
        if not skipped:
            await message.answer("Нужен файл-документ. Пришлите ещё раз:")
        return
    jsessions = [n for n in files if n.lower().endswith(".jsession")]
    if jsessions and len(files) > 1:
        await message.answer("Файл .jsession присылайте отдельно, по одному. Пришлите ещё раз:")
        return
    if jsessions and len(files[jsessions[0]]) > MAX_SESSION_BYTES:
        await message.answer("Файл слишком большой для сессии. Пришлите .jsession ещё раз:")
        return
    await _import(message, state, files, None, sysd)


async def _import(message: Message, state: FSMContext, files: dict, passcode: Optional[str],
                  sysd: Systemd) -> None:
    """tdata / .session (+ .json) / .jsession: checked by connecting, saved as a .jsession."""
    await message.answer("⏳ Проверяю сессию: подключаюсь к аккаунту…")
    try:
        saved = await session_import.import_files(files, projects.SESSIONS_DIR, passcode)
    except session_import.NeedPasscode as e:
        await ask(message, state, UploadSession.passcode,
                  f"🔐 {esc(e)}. Пришлите код-пароль Telegram Desktop (сообщение удалю, он не сохраняется):",
                  files=files)
        return
    except session_import.SessionImportError as e:
        await ask(message, state, UploadSession.file, f"⚠️ Не загружено: {esc(e)}. Пришлите другие файлы:")
        return
    path = os.path.relpath(saved, projects.REPO_DIR)
    logger.info("panel: session %s imported", path)
    await session_ready(message, state, path, f"✅ Сессия {esc(account_label(path))} сохранена.", sysd)


@router.message(UploadSession.passcode)
async def on_passcode(message: Message, state: FSMContext, sysd: Systemd) -> None:
    passcode = message.text or ""
    await delete_quietly(message)
    files = (await state.get_data()).get("files")
    if not files:
        await end_form(message, state, "Файлы потерялись — начните заново.")
        return
    if not passcode:
        await message.answer("Нужен код-пароль текстом. Пришлите ещё раз:")
        return
    await _import(message, state, files, passcode, sysd)


# ── 🔑 Войти по номеру ──────────────────────────────────────────────────────

PHONE_ASK = (
    f"{head(title('acc_login'))} — пришлите номер телефона в международном формате, "
    "например <code>+79991234567</code>. Вход идёт с профилем Telegram Desktop, как "
    "у <code>python login.py</code>."
)
CODE_ASK = (
    "Пришлите код <b>через пробелы</b>, например <code>1 2 3 4 5</code>: код, отправленный "
    "в Telegram целиком, Telegram аннулирует. Сообщение с кодом я удалю."
)


def resend_kb():
    return choice_kb("login_resend", [("📲 Отправить код заново", "resend")])


def make_client():
    """The sign-in client (TDesktop fingerprint, a fresh session); tests replace it."""
    from telethon import TelegramClient

    client = TelegramClient(
        StringSession(), TDESKTOP_APP["api_id"], TDESKTOP_APP["api_hash"],
        device_model=TDESKTOP_APP["device_name"], system_version=TDESKTOP_APP["sdk"],
        app_version=TDESKTOP_APP["app_version"], system_lang_code=TDESKTOP_APP["system_lang_code"],
    )
    apply_lang_pack(client, TDESKTOP_APP["lang_pack"])
    return client


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


async def _fail(message: Message, state: FSMContext, text: str) -> None:
    await logins.close(message.chat.id)
    await end_form(message, state, text)


@router.message(Login.phone)
async def on_phone(message: Message, state: FSMContext) -> None:
    phone = normalize_phone(message.text or "")
    if phone is None:
        await message.answer("Не похоже на номер. Пришлите его в формате +79991234567:")
        return
    await logins.close(message.chat.id)
    client = make_client()
    try:
        await _timed(client.connect())
        sent = await _timed(client.send_code_request(f"+{phone}"))
    except errors.FloodWaitError as e:
        await logins.close(message.chat.id)
        await client.disconnect()
        await end_form(message, state, f"⚠️ Слишком много попыток, подождите {e.seconds} с.")
        return
    except Exception as e:  # noqa: BLE001 - shown to the admin, the form ends
        await client.disconnect()
        await end_form(message, state, f"⚠️ Код не отправлен: {esc(e) or 'Telegram не ответил'}.")
        return
    logins.put(message.chat.id, logins.Login(client, phone, sent.phone_code_hash))
    await ask(message, state, Login.code, f"📲 Код отправлен.\n{CODE_ASK}", resend_kb())


@router.callback_query(Login.code, ChoiceCB.filter(F.scope == "login_resend"))
async def on_resend(callback: CallbackQuery, state: FSMContext) -> None:
    login = logins.get(callback.from_user.id)
    if login is None:
        await stale_tap(callback, "Вход устарел — начните заново.")
        return
    await callback.answer()
    try:
        sent = await _timed(login.client.send_code_request(f"+{login.phone}"))
    except errors.FloodWaitError as e:
        await message_of(callback).answer(f"⚠️ Слишком много попыток, подождите {e.seconds} с.")
        return
    except Exception as e:  # noqa: BLE001 - the step stays: the old code may still work
        await message_of(callback).answer(f"⚠️ Код не отправлен: {esc(e) or 'Telegram не ответил'}.")
        return
    login.phone_code_hash = sent.phone_code_hash
    await ask(message_of(callback), state, Login.code, f"📲 Новый код отправлен.\n{CODE_ASK}", resend_kb())


@router.message(Login.code)
async def on_code(message: Message, state: FSMContext, sysd: Systemd) -> None:
    login = logins.get(message.chat.id)
    code = code_digits(message.text or "")
    await delete_quietly(message)
    if login is None:
        await end_form(message, state, "Вход устарел — начните заново.")
        return
    if code is None:
        await message.answer(CODE_ASK)
        return
    try:
        await _timed(login.client.sign_in(f"+{login.phone}", code, phone_code_hash=login.phone_code_hash))
    except errors.SessionPasswordNeededError:
        await ask(message, state, Login.password,
                  "🔐 У аккаунта включён пароль 2FA. Пришлите его (сообщение удалю, пароль не сохраняется):")
        return
    except errors.PhoneCodeInvalidError:
        await message.answer(f"Неверный код. {CODE_ASK}")
        return
    except errors.PhoneCodeExpiredError:
        await ask(message, state, Login.code,
                  "⌛ Код истёк (или Telegram аннулировал его, увидев целиком). Запросите новый и "
                  "пришлите его через пробелы.", resend_kb())
        return
    except errors.FloodWaitError as e:
        await message.answer(f"⚠️ Слишком много попыток, подождите {e.seconds} с и пришлите код снова.")
        return
    except Exception as e:  # noqa: BLE001
        await _fail(message, state, f"⚠️ Вход не удался: {esc(e) or 'Telegram не ответил'}")
        return
    await _finish(message, state, login, sysd)


@router.message(Login.password)
async def on_password(message: Message, state: FSMContext, sysd: Systemd) -> None:
    login = logins.get(message.chat.id)
    password = message.text or ""
    await delete_quietly(message)
    if login is None:
        await end_form(message, state, "Вход устарел — начните заново.")
        return
    if not password:
        await message.answer("Нужен пароль текстом. Пришлите ещё раз:")
        return
    try:
        await _timed(login.client.sign_in(password=password))
    except errors.PasswordHashInvalidError:
        await message.answer("Неверный пароль. Пришлите ещё раз:")
        return
    except errors.FloodWaitError as e:
        await message.answer(f"⚠️ Слишком много попыток, подождите {e.seconds} с и пришлите пароль снова.")
        return
    except Exception as e:  # noqa: BLE001
        await _fail(message, state, f"⚠️ Вход не удался: {esc(e) or 'Telegram не ответил'}")
        return
    await _finish(message, state, login, sysd)


async def _finish(message: Message, state: FSMContext, login: logins.Login, sysd: Systemd) -> None:
    """Signed in: save the session (an old file of this number is kept as .bak)."""
    try:
        me = await login.client.get_me()
        path = f"sessions/{me.phone or login.phone}.jsession"
        save_jsession(str(projects.REPO_DIR / path), login.client.session.save(), me, TDESKTOP_APP)
    except Exception as e:  # noqa: BLE001
        await _fail(message, state, f"⚠️ Аккаунт не сохранён: {esc(e)}")
        return
    await logins.close(message.chat.id)
    logger.info("panel: signed in %s", path)
    await session_ready(message, state, path, f"✅ Вход выполнен: {esc(account_label(path))}.", sysd)


@router.callback_query(ChoiceCB.filter(F.scope == "acc_pick"))
async def on_pick(callback: CallbackQuery, callback_data: ChoiceCB, state: FSMContext, sysd: Systemd) -> None:
    """An account picker (a new project's, a project's 👤 Аккаунт)."""
    if await ask_account(callback, state, callback_data.value):
        return
    paths = (await state.get_data()).get("accounts") or []
    index = int(callback_data.value) if callback_data.value.isdigit() else -1
    if not 0 <= index < len(paths):
        await stale_tap(callback)
        return
    await callback.answer()
    await message_of(callback).edit_reply_markup(reply_markup=None)
    await session_ready(message_of(callback), state, paths[index], "", sysd)


def picker(paths: list):
    return choice_kb("acc_pick", account_choices(paths))
