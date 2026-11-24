"""The last router: a button no handler took — an old message's, a step left
since — and a message no step took. Answered, or nothing would happen."""

from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.keyboards.menu import main_menu
from bot.routers._common import stale_tap

router = Router(name="stale")


@router.callback_query()
async def on_stale_button(callback: CallbackQuery) -> None:
    await stale_tap(callback)


@router.message(StateFilter(None))
async def on_no_step(message: Message) -> None:
    # the keyboard again too: it may have been hidden
    await message.answer(texts.USE_MENU, reply_markup=main_menu())


@router.message()
async def on_button_step(message: Message) -> None:
    await message.answer(texts.USE_BUTTONS)
