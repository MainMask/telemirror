"""edit_message must send the mirror's new text verbatim: for a source message
with no formatting (`entities is None`), Telethon's unpatched
`client.edit_message` would otherwise run the text through the client's
markdown parse_mode, turning `**2**` bold and `[a](b)` into a hidden link."""

import logging

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl import functions, types

from config import DirectionConfig
from telemirror.messagefilters import EmptyMessageFilter
from telemirror.mirroring import EventProcessor
from telemirror.storage import InMemoryDatabase, MirrorMessage
from tests.conftest import make_message, run

SOURCE = -1001000000000
TARGET = -1002000000001


def test_edit_without_entities_is_not_markdown_parsed():
    captured = []

    class _CapturingClient(TelegramClient):
        async def get_input_entity(self, peer):
            return types.InputPeerChannel(1, 0)

        async def __call__(self, request, ordered=False, flood_sleep_threshold=None):
            captured.append(request)
            raise RuntimeError("captured")

    client = _CapturingClient(StringSession(), 1, "x")
    client.parse_mode = "markdown"  # as build_telegram_client sets it

    db = run(InMemoryDatabase())
    run(db.insert(MirrorMessage(100, SOURCE, 5000, TARGET)))
    proc = EventProcessor(
        chat_mapping={
            SOURCE: {
                TARGET: [
                    DirectionConfig(
                        disable_delete=False, disable_edit=False,
                        filters=EmptyMessageFilter(),
                    )
                ]
            }
        },
        database=db,
        client=client,
        logger=logging.getLogger("test.edit_markdown"),
    )
    text = "snake__case and **2**x [a](b)"
    msg = make_message(text, entities=None)
    msg.id = 100

    run(proc.edit_message(SOURCE, msg, "link"))

    edits = [r for r in captured if isinstance(r, functions.messages.EditMessageRequest)]
    assert edits[0].message == text
    assert not edits[0].entities
