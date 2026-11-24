"""/start, /status, /cancel, the main menu and every screen's opening — the
first router, so a main-menu button or a command always escapes a form."""

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import status, texts
from bot.pending import Picker
from bot.pending import close as close_pending
from bot.pending import put as hold
from bot.callbacks import ChoiceCB, NavCB
from bot.configparse import ConfigError
from bot.keyboards.menu import chat_picker, main_menu
from bot.registry import BY_TITLE, MAIN_MENU, SCREENS, TASKS, menu_path, title
from bot.routers._common import (
    CONFIRMED,
    INPUTS,
    end_form,
    message_of,
    project_of,
    remember_chat,
    retry,
    stale_tap,
    take_confirm,
)
from bot.screens import open_screen
from bot.states import Input, leave_form
from bot.systemd import Systemd
from bot.texts import esc, head
from telemirror.projects import list_projects

router = Router(name="menu")

# typed inputs that take a channel: a forwarded post from it will do
CHAT_INPUTS = frozenset({"dir_src", "dir_dst", "dir_find", "global", "sp_only"})


async def welcome(name: str, sysd: Systemd) -> str:
    found = list_projects()
    running = 0
    for p in found:
        st = await status.unit_state(sysd, p.live_unit)
        running += bool(st and st.running)
    sections = "\n".join(f"{head(t)} — {esc(BY_TITLE[t].hint)}" for t in MAIN_MENU)
    return (
        f"👋 Здравствуйте, <b>{esc(name or 'администратор')}</b>!\n\n"
        "Добро пожаловать в <b>Telemirror</b> — панель управления зеркалированием "
        "Telegram-каналов.\n\n"
        f"📁 Проектов: <b>{len(found)}</b> · 🟢 зеркал работает: <b>{running}</b>\n\n"
        f"{sections}\n\n"
        + texts.more(
            "<b>Как начать</b>\n"
            f"1. Войдите в аккаунт Telegram, от имени которого копировать: {esc(menu_path('acc_login'))}.\n"
            f"2. Создайте проект: {esc(menu_path('new'))}.\n"
            f"3. В проекте откройте {esc(SCREENS['dirs'].title)} и добавьте, откуда и куда копировать, "
            f"затем нажмите {esc(title('start'))}."
        ) + "\n\n"
        "/status — что сейчас работает · /cancel — выйти из ввода\n\n"
        f"<i>{texts.USE_MENU}</i>"
    )


@router.message(CommandStart())
async def on_start(message: Message, state: FSMContext, sysd: Systemd) -> None:
    await close_pending(message.chat.id, quiet=True)  # its answer puts the main menu back itself
    await leave_form(message.chat.id, state)
    name = message.from_user.first_name if message.from_user else ""
    await message.answer(await welcome(name, sysd), reply_markup=main_menu())


@router.message(F.text.in_(MAIN_MENU))
async def on_main_menu(message: Message, state: FSMContext, deps: dict) -> None:
    await leave_form(message.chat.id, state)
    await open_screen(NavCB(s=BY_TITLE[message.text or ""].id), message, False, deps)


@router.message(Command("status"))
async def on_status(message: Message, deps: dict) -> None:
    # Only shows: a form under way stays at its step.
    await open_screen(NavCB(s=BY_TITLE[TASKS].id), message, False, deps)


async def cancel(message: Message, state: FSMContext, deps: dict, edit: bool) -> None:
    """Out of the form (or a pending «Да»), straight back to the screen it began on."""
    data = await state.get_data()
    back = data.get("origin") or (data.get("confirm") or {}).get("back")
    await leave_form(message.chat.id, state)
    if back:
        await open_screen(NavCB.unpack(back), message, edit, deps, note=texts.CANCELLED)
    else:
        await message.answer(texts.CANCELLED, reply_markup=main_menu())


@router.message(Command("cancel"))
async def on_cancel(message: Message, state: FSMContext, deps: dict) -> None:
    if await state.get_state() is not None:
        await cancel(message, state, deps, edit=False)
        return
    await message.answer(
        "Сейчас нечего отменять. Остановить зеркало, копирование старых постов или инструмент — "
        f"на их экране в проекте; что сейчас работает — в {TASKS}.", reply_markup=main_menu()
    )


@router.callback_query(NavCB.filter(F.s.in_(SCREENS)))
async def on_nav(callback: CallbackQuery, callback_data: NavCB, deps: dict) -> None:
    await callback.answer()
    await open_screen(callback_data, message_of(callback), True, deps)


@router.callback_query(ChoiceCB.filter(F.scope == "pick"))
async def on_pick(callback: CallbackQuery, state: FSMContext) -> None:
    """📇 Выбрать из списка under a prompt: Telegram's list of the admin's chats
    at the bottom; the form stays at its step (a ChoiceCB)."""
    if await state.get_state() is None:
        await stale_tap(callback)
        return
    await callback.answer()
    await message_of(callback).answer(texts.PICK_ASK, reply_markup=chat_picker())
    # left without a pick, the form puts the main menu back (pending.Picker)
    await hold(callback.from_user.id, Picker(callback.bot))


@router.callback_query(ChoiceCB.filter(F.scope == "cancel"))
async def on_cancel_button(callback: CallbackQuery, callback_data: ChoiceCB, state: FSMContext,
                           deps: dict) -> None:
    """✖️ Отмена under a prompt: as /cancel, only while still at its step —
    the screen in the prompt's place."""
    if await state.get_state() != callback_data.value.replace(".", ":"):
        await stale_tap(callback)
        return
    await callback.answer()
    await cancel(message_of(callback), state, deps, edit=True)


@router.callback_query(ChoiceCB.filter(F.scope.in_({"yes", "no"})))
async def on_confirm(callback: CallbackQuery, callback_data: ChoiceCB, state: FSMContext, deps: dict,
                     **rest) -> None:
    pending = await take_confirm(callback, state, callback_data.value)
    if pending is None:
        return
    if callback_data.scope == "no":
        await callback.answer()
        await open_screen(NavCB.unpack(pending["back"]), message_of(callback), True, deps)
        return
    project = None
    if pending.get("p") and (project := await project_of(callback, pending["p"])) is None:
        return
    await CONFIRMED[pending["kind"]](callback, pending, state=state, project=project, deps=deps, **rest)


@router.message(Input.value)
async def on_input(message: Message, state: FSMContext, deps: dict, **rest) -> None:
    form = await state.get_data()
    handler = INPUTS.get(form.get("kind", ""))
    if handler is None:
        await end_form(message, state, texts.STALE_BUTTON)
        return
    project = None
    if form.get("p"):
        if (project := await project_of(message, form["p"])) is None:
            await leave_form(message.chat.id, state)
            return
    try:
        takes_chat = form.get("kind") in CHAT_INPUTS or form.get("arg_kind") == "ids"  # a filter's channels
        forwarded = remember_chat(project, message) if project and takes_chat else None
    except ConfigError as e:
        await retry(message, e)
        return
    raw = forwarded or (message.text or "").strip()
    if not raw:
        await message.answer(texts.NEED_TEXT)
        return
    try:
        await handler(message, state=state, raw=raw, data=form, project=project, deps=deps, **rest)
    except ConfigError as e:  # a refused value: the same step again
        await retry(message, e)
