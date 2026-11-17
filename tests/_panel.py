"""Shared fakes for the panel tests: a recording Bot API session, a scripted
systemd runner, and helpers that feed real updates through the Dispatcher."""

from datetime import datetime
from itertools import count
from typing import Any, AsyncGenerator

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.methods import EditMessageText, GetMe, SendMessage
from aiogram.types import CallbackQuery, Chat, Message, Update, User

ADMIN_ID = 1001
STRANGER_ID = 2002

SHOW = """\
ActiveState={active}
SubState={sub}
Result={result}
ActiveEnterTimestamp=@1763380000
InactiveEnterTimestamp=@1763390000
NRestarts=0
MemoryCurrent=524288000
InvocationID=abc
LoadState=loaded
"""


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list = []
        self._ids = count(500)

    async def make_request(self, bot: Bot, method: Any, timeout: Any = None) -> Any:
        self.requests.append(method)
        if isinstance(method, GetMe):
            return User(id=42, is_bot=True, first_name="panel", username="panel_bot")
        if isinstance(method, (SendMessage, EditMessageText)):
            mid = getattr(method, "message_id", None) or next(self._ids)
            return Message(
                message_id=mid, date=datetime.now(),
                chat=Chat(id=int(method.chat_id or 0), type="private"), text=method.text,
            )
        return True

    async def close(self) -> None:
        pass

    async def stream_content(  # pragma: no cover
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:
        raise NotImplementedError
        yield b""

    def of(self, kind: type) -> list:
        return [r for r in self.requests if isinstance(r, kind)]

    def last_text(self) -> str:
        sent = [r for r in self.requests if isinstance(r, (SendMessage, EditMessageText))]
        return str(sent[-1].text)


class FakeSystemd:
    """Scripted runner: unit → ActiveState; records control commands."""

    def __init__(self, states: dict | None = None) -> None:
        self.states = states or {}
        self.calls: list = []

    async def __call__(self, argv):
        self.calls.append(list(argv))
        if argv[:2] == ["systemctl", "show"]:
            active = self.states.get(argv[2], "inactive")
            sub = "running" if active == "active" else "dead"
            return 0, SHOW.format(active=active, sub=sub, result="success")
        if argv[0] == "journalctl":
            return 0, "line one\nline <two>"
        return 0, ""


def make_bot() -> tuple[Bot, FakeSession]:
    session = FakeSession()
    bot = Bot("42:TEST", session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    return bot, session


def _user(uid: int) -> User:
    return User(id=uid, is_bot=False, first_name="Даниил <b>")


_upd = count(1)


def message_update(text: str, uid: int = ADMIN_ID) -> Update:
    return Update(
        update_id=next(_upd),
        message=Message(
            message_id=next(_upd) + 10_000, date=datetime.now(),
            chat=Chat(id=uid, type="private"), from_user=_user(uid), text=text,
        ),
    )


def callback_update(data: str, uid: int = ADMIN_ID, message_id: int = 77) -> Update:
    return Update(
        update_id=next(_upd),
        callback_query=CallbackQuery(
            id=str(next(_upd)), from_user=_user(uid), chat_instance="ci", data=data,
            message=Message(
                message_id=message_id, date=datetime.now(),
                chat=Chat(id=uid, type="private"), text="panel",
            ),
        ),
    )
