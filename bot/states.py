"""The forms: one StatesGroup per multi-step form (its FSM data keys are named
where they are set), ``Input`` for one typed value, ``Confirm`` for a pending
«Да». Leaving a form and the panel's FSM storage live here too."""

from typing import Any, Mapping

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.base import StateType, StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot import pending


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
    """One typed value; FSM data ``kind`` says which (``routers._common.input_kind``)."""

    value = State()


class UploadConfig(StatesGroup):
    file = State()  # data: p — then the replacement is confirmed (Confirm)


class Confirm(StatesGroup):
    """A confirmation on screen (data: confirm = the pending action + token)."""

    pending = State()


async def leave_form(chat_id: int, state: FSMContext) -> None:
    """Out of any form; what it kept outside the FSM (a sign-in waiting for
    its code, uploaded files) is dropped now."""
    await pending.close(chat_id)
    await state.clear()


class PanelStorage(MemoryStorage):
    """MemoryStorage that keeps only chats in a form: reading a chat's state
    doesn't create its record (the stock ``defaultdict`` does — for every
    update, before AdminOnly drops a stranger's), and a cleared one is dropped."""

    async def get_state(self, key: StorageKey) -> str | None:
        record = self.storage.get(key)
        return record.state if record else None

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        record = self.storage.get(key)
        return record.data.copy() if record else {}

    async def get_value(self, storage_key: StorageKey, dict_key: str, default: Any | None = None) -> Any | None:
        return (await self.get_data(storage_key)).get(dict_key, default)

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        await super().set_state(key, state)
        self._drop_if_empty(key)

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        await super().set_data(key, data)
        self._drop_if_empty(key)

    def _drop_if_empty(self, key: StorageKey) -> None:
        record = self.storage.get(key)
        if record is not None and record.state is None and not record.data:
            del self.storage[key]
