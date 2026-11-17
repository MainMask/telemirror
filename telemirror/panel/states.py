"""One StatesGroup per form. Its FSM data keys are named where they are set."""

from aiogram.fsm.state import State, StatesGroup


class NewProject(StatesGroup):
    name = State()  # typed
    icon = State()  # data: name — a button or a typed emoji
    account = State()  # data: name, icon, accounts (the listed session paths)


class Login(StatesGroup):
    """Sign-in by phone (data: then — "new" / "<project key>" / "" for the
    accounts list: where the new session goes once saved)."""

    phone = State()
    code = State()
    password = State()


class UploadSession(StatesGroup):
    file = State()  # data: then, as Login
    passcode = State()  # data: then, files — a tdata encrypted with Telegram Desktop's passcode


class AddDirection(StatesGroup):
    source = State()  # data: p
    targets = State()  # data: p, source
    choice = State()  # data: p, source, targets, mode, history — buttons only


class Input(StatesGroup):
    """One typed value; FSM data ``kind`` says which (routers/inputs.py)."""

    value = State()


class UploadConfig(StatesGroup):
    file = State()  # data: p
    confirm = State()  # data: p, text, sha


class Confirm(StatesGroup):
    """A confirmation on screen (data: confirm = the pending action + token)."""

    pending = State()
