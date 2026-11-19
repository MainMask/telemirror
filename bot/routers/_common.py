"""What every router shares: actions bound to registry buttons (their project
loaded once, here), forms (start, cancel back to where they began), typed
inputs, confirmations, refusals."""

import functools
import inspect
import logging
import secrets
import time
from contextlib import suppress
from typing import Awaitable, Callable, Optional, Union

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot import settings, status, texts
from bot.callbacks import ActCB, NavCB
from bot.configparse import ConfigError
from bot.keyboards.common import back_kb, cancel_kb, confirm_kb
from bot.registry import YES
from bot.states import Confirm, leave_form
from bot.systemd import Systemd
from telemirror.projects import Project, save_chat_names

logger = logging.getLogger(__name__)

# ── registry buttons ↔ handlers (checked at startup: app.build_dispatcher) ──
HANDLED: set = set()


def with_project(factory: type[CallbackData]):
    """A project's button (``factory`` data with ``p``): its handler gets
    ``project`` loaded — a deleted project is answered here, once."""

    def register(handler):
        wants = "project" in inspect.signature(handler).parameters

        @functools.wraps(handler)  # aiogram passes the handler's own parameters
        async def wrapped(callback: CallbackQuery, *args, **kwargs):
            key = getattr(factory.unpack(callback.data or ""), "p", "")
            if key:
                project = status.find(key)
                if project is None:
                    await stale_tap(callback, texts.NO_PROJECT)
                    return None
                if wants:
                    kwargs["project"] = project
            return await handler(callback, *args, **kwargs)

        return wrapped

    return register


def on_action(router: Router, *actions: str):
    """Register the handler for these registry actions (ActCB.a)."""
    HANDLED.update(actions)

    def register(handler):
        router.callback_query(ActCB.filter(F.a.in_(set(actions))))(with_project(ActCB)(handler))
        return handler

    return register


def message_of(callback: CallbackQuery) -> Message:
    """The message under the tapped button. The panel's buttons are on its own
    messages, so it's there; an inaccessible one (deleted) can't be edited
    anyway — the error handler reports it."""
    if not isinstance(callback.message, Message):
        raise RuntimeError("the message of the tapped button is inaccessible")
    return callback.message


def forwarded_chat(message: Message) -> Optional[tuple]:
    """(chat id, title) of the channel (or group, posting as itself) a
    forwarded post comes from; None for anything else."""
    origin = message.forward_origin
    chat = getattr(origin, "chat", None) or getattr(origin, "sender_chat", None)
    if chat is None:
        return None
    return chat.id, chat.title or ""


def remember_chat(project: Project, message: Message) -> Optional[str]:
    """A forwarded post's channel — or one picked with 📇 Выбрать из списка —
    as a typed id (``-100…``), its title kept for the screens; None when the
    message is neither. A forward from a person (or a hidden author) names no
    channel: ConfigError."""
    if (picked := message.chat_shared) is not None:
        if picked.title:
            save_chat_names(project.key, {picked.chat_id: picked.title})
        return str(picked.chat_id)
    if message.forward_origin is None:
        return None
    found = forwarded_chat(message)
    if found is None:
        raise ConfigError("not_channel")
    chat_id, title = found
    if title:
        save_chat_names(project.key, {chat_id: title})
    return str(chat_id)


async def stale_tap(callback: CallbackQuery, text: str = texts.STALE_BUTTON) -> None:
    await callback.answer(text, show_alert=True)


async def project_of(event: Union[CallbackQuery, Message], key: str) -> Optional[Project]:
    """A form's project (by its FSM data); None after saying it's gone."""
    project = status.find(key)
    if project is None:
        if isinstance(event, CallbackQuery):
            await stale_tap(event, texts.NO_PROJECT)
        else:
            await event.answer(texts.NO_PROJECT, reply_markup=back_kb(NavCB(s="prj")))
    return project


async def session_ok(callback: CallbackQuery, project: Project) -> bool:
    """False after saying so: the project's session file is gone — nothing can
    run on it (and its config can't be validated)."""
    if project.session_path.exists():
        return True
    await stale_tap(callback, texts.SESSION_MISSING)
    return False


async def systemd_ready(callback: CallbackQuery, sysd: Systemd) -> bool:
    if sysd.available:
        return True
    await stale_tap(callback, texts.SYSTEMD_UNAVAILABLE)
    return False


# ── forms ───────────────────────────────────────────────────────────────────


async def start_form(
    callback: CallbackQuery,
    state: FSMContext,
    step,
    text: str,
    origin: NavCB,
    *,
    markup: Optional[InlineKeyboardMarkup] = None,
    data: Optional[dict] = None,
    choice: bool = False,
) -> None:
    """The chat at ``step`` (a form before it left), ``data`` kept for the next
    steps, ``origin`` — where ✖️ Отмена and /cancel return. The prompt (``text``,
    HTML, starting with the form's title in bold) with ✖️ Отмена under its own
    buttons: for typed input a new message (the screen stays above); ``choice``
    (a step answered only by buttons) in the screen's place."""
    await callback.answer()
    await leave_form(callback.from_user.id, state)
    await state.set_state(step)
    await state.update_data(origin=origin.pack(), **(data or {}))
    send = message_of(callback).edit_text if choice else message_of(callback).answer
    await send(text, reply_markup=cancel_kb(step.state, markup))


async def ask(message: Message, state: FSMContext, step, text: str,
              markup: Optional[InlineKeyboardMarkup] = None, **data) -> None:
    """The form's next step: its prompt as a new message, ✖️ Отмена under it."""
    await state.set_state(step)
    if data:
        await state.update_data(**data)
    await message.answer(text, reply_markup=cancel_kb(step.state, markup))


async def origin_of(state: FSMContext) -> Optional[NavCB]:
    raw = (await state.get_data()).get("origin")
    return NavCB.unpack(raw) if raw else None


async def end_form(message: Message, state: FSMContext, text: str, edit: bool = False) -> None:
    """A form's last word (a refusal, a cancel) with ⬅️ to where it began."""
    back = await origin_of(state)
    await leave_form(message.chat.id, state)
    kb = back_kb(back) if back else None
    await (message.edit_text if edit else message.answer)(text, reply_markup=kb)


async def retry(message: Message, error: ConfigError) -> None:
    """A refused typed value: why, and the same step again."""
    await message.answer(texts.retry(error.code, error.detail))


async def delete_quietly(message: Message) -> None:
    """Best effort: a password or a login code must not stay in the chat."""
    with suppress(TelegramBadRequest):
        await message.delete()


# ── typed inputs: one Input.value step, its meaning in FSM data "kind" ──────
# A handler gets (message, *, state, raw, data, project=<data["p"]'s>, deps,
# **services) and may raise ConfigError for a refused value: the step is asked
# again (routers.menu.on_input).
InputHandler = Callable[..., Awaitable[None]]
INPUTS: dict = {}


def input_kind(kind: str):
    def register(function: InputHandler) -> InputHandler:
        INPUTS[kind] = function
        return function
    return register


# ── confirmations ───────────────────────────────────────────────────────────
# A handler gets (callback, action: dict, *, state, project=<action["p"]'s>, deps, **services).
Confirmed = Callable[..., Awaitable[None]]
CONFIRMED: dict = {}


def confirmed(kind: str):
    """Register what a confirmation of ``kind`` runs once «Да» is pressed."""
    def register(function: Confirmed) -> Confirmed:
        CONFIRMED[kind] = function
        return function
    return register


async def ask_confirm(
    event: Union[CallbackQuery, Message], state: FSMContext, text: str, kind: str, back: NavCB,
    yes: str = YES, **action,
) -> None:
    """The confirmation — in the screen's place (a button's ``event``) or as a
    new message (after a typed step or a file): ``yes`` | ✖️ Отмена. Only the
    latest one is valid (a token), and only for ``CONFIRM_TTL_SEC``; ✖️ Отмена
    shows ``back`` again."""
    out: Callable[..., Awaitable]  # edit the screen or send a new message
    if isinstance(event, CallbackQuery):
        await event.answer()
        chat_id, out = event.from_user.id, message_of(event).edit_text
    else:
        chat_id, out = event.chat.id, event.answer
    token = secrets.token_hex(4)
    await leave_form(chat_id, state)
    await state.set_state(Confirm.pending)
    await state.update_data(confirm={
        "kind": kind, "token": token, "at": time.time(), "back": back.pack(), **action,
    })
    await out(text, reply_markup=confirm_kb(token, yes))


async def take_confirm(callback: CallbackQuery, state: FSMContext, token: str) -> Optional[dict]:
    """The pending action this «Да» / ✖️ belongs to; None after saying why not."""
    pending = (await state.get_data()).get("confirm") if await state.get_state() == Confirm.pending.state else None
    if not pending or pending.get("token") != token:
        await stale_tap(callback)
        return None
    if time.time() - pending["at"] > settings.CONFIRM_TTL_SEC:
        await state.clear()
        await stale_tap(callback, texts.CONFIRM_EXPIRED)
        return None
    await state.clear()
    return pending
