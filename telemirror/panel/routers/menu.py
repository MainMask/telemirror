"""/start, /status, /cancel, the main menu and every screen's opening — the
first router, so a main-menu button or a command always escapes a form."""

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from telemirror.panel import status, texts
from telemirror.panel.callbacks import ChoiceCB, NavCB
from telemirror.panel.keyboards.menu import main_menu
from telemirror.panel.registry import BY_TITLE, MAIN_MENU, SCREENS, TASKS
from telemirror.panel.routers._common import (
    CONFIRMED,
    INPUTS,
    end_form,
    leave_form,
    message_of,
    stale_tap,
    take_confirm,
)
from telemirror.panel.screens import esc, head, open_screen
from telemirror.panel.states import Input
from telemirror.panel.systemd import Systemd
from telemirror.projects import list_projects

router = Router(name="menu")


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
        "/status — что сейчас выполняется · /cancel — выйти из ввода\n\n"
        "<i>Выберите раздел в меню ниже 👇</i>"
    )


@router.message(CommandStart())
async def on_start(message: Message, state: FSMContext, sysd: Systemd) -> None:
    await leave_form(message.chat.id, state)
    name = message.from_user.first_name if message.from_user else ""
    await message.answer(await welcome(name, sysd), reply_markup=main_menu())


@router.message(F.text.in_(MAIN_MENU))
async def on_main_menu(message: Message, state: FSMContext, **deps) -> None:
    await leave_form(message.chat.id, state)
    await open_screen(NavCB(s=BY_TITLE[message.text or ""].id), message, False, state, deps)


@router.message(Command("status"))
async def on_status(message: Message, state: FSMContext, **deps) -> None:
    # Only shows: a form under way stays at its step.
    await open_screen(NavCB(s=BY_TITLE[TASKS].id), message, False, state, deps)


@router.message(Command("cancel"))
async def on_cancel(message: Message, state: FSMContext) -> None:
    if await state.get_state() is not None:
        await end_form(message, state, texts.CANCELLED)
        return
    await message.answer(
        f"Сейчас нечего отменять. Остановить задачу — в {TASKS}.", reply_markup=main_menu()
    )


@router.callback_query(NavCB.filter(F.s.in_(SCREENS)))
async def on_nav(callback: CallbackQuery, callback_data: NavCB, state: FSMContext, **deps) -> None:
    await callback.answer()
    await open_screen(callback_data, message_of(callback), True, state, deps)


@router.callback_query(ChoiceCB.filter(F.scope == "cancel"))
async def on_cancel_button(callback: CallbackQuery, callback_data: ChoiceCB, state: FSMContext) -> None:
    """✖️ Отмена under a prompt: as /cancel, only while still at its step."""
    if await state.get_state() != callback_data.value.replace(".", ":"):
        await stale_tap(callback)
        return
    await callback.answer()
    await end_form(message_of(callback), state, texts.CANCELLED, edit=True)


@router.callback_query(ChoiceCB.filter(F.scope.in_({"yes", "no"})))
async def on_confirm(callback: CallbackQuery, callback_data: ChoiceCB, state: FSMContext, **deps) -> None:
    pending = await take_confirm(callback, state, callback_data.value)
    if pending is None:
        return
    if callback_data.scope == "no":
        await callback.answer()
        await open_screen(NavCB.unpack(pending["back"]), message_of(callback), True, state, deps)
        return
    await CONFIRMED[pending["kind"]](callback, pending, state, **deps)


@router.message(Input.value)
async def on_input(message: Message, state: FSMContext, **deps) -> None:
    data = await state.get_data()
    handler = INPUTS.get(data.get("kind", ""))
    if handler is None:
        await end_form(message, state, texts.STALE_BUTTON)
        return
    raw = (message.text or "").strip()
    if not raw:
        await message.answer("Нужен текст. Пришлите ещё раз:")
        return
    await handler(message, state, raw, data, **deps)
