"""copy_message preserves `invert_media`/`effect` (see test_mixins.py); this
covers the other half — that new_message's primary copy-mode send actually
forwards them to send_message instead of leaving them stranded on the
(unread) filtered_message object."""

import logging

from telethon.tl import types

import telemirror.mirroring as mirroring
from config import DirectionConfig
from telemirror.messagefilters import EmptyMessageFilter
from telemirror.mirroring import EventProcessor
from telemirror.storage import InMemoryDatabase
from tests.conftest import make_message, run

SOURCE = -1001000000000
TARGET = -1002000000001


def _cfg():
    return DirectionConfig(
        disable_delete=False, disable_edit=False, filters=EmptyMessageFilter()
    )


def test_new_message_copy_mode_forwards_invert_media_and_effect(monkeypatch):
    db = run(InMemoryDatabase())
    calls = []

    async def fake_send_message(client, entity, message, **kw):
        calls.append((kw.get("invert_media"), kw.get("message_effect_id")))
        return types.Message(id=555, peer_id=types.PeerChannel(1), message="x")

    monkeypatch.setattr(mirroring, "send_message", fake_send_message)

    proc = EventProcessor(
        chat_mapping={SOURCE: {TARGET: [_cfg()]}},
        database=db,
        client=object(),
        logger=logging.getLogger("test.invert_media"),
    )

    msg = make_message("x", channel_id=1000)
    msg.invert_media = True
    msg.effect = 123

    run(proc.new_message(SOURCE, msg, "link"))

    assert calls == [(True, 123)]


def test_new_album_copy_mode_forwards_invert_media_and_effect(monkeypatch):
    """new_message forwards invert_media/effect (see above); new_album must
    too — Telegram's SendMultiMediaRequest takes both as one flag for the
    whole album, so the first item's value represents the group."""
    db = run(InMemoryDatabase())
    calls = []

    async def fake_send_file(client, entity, caption, file, **kw):
        calls.append((kw.get("invert_media"), kw.get("message_effect_id")))
        return [
            types.Message(id=900 + i, peer_id=types.PeerChannel(1), message="")
            for i in range(len(file))
        ]

    monkeypatch.setattr(mirroring, "send_file", fake_send_file)

    proc = EventProcessor(
        chat_mapping={SOURCE: {TARGET: [_cfg()]}},
        database=db,
        client=object(),
        logger=logging.getLogger("test.invert_media_album"),
    )

    album = [
        make_message("a", media=types.MessageMediaUnsupported(), channel_id=1000),
        make_message("b", media=types.MessageMediaUnsupported(), channel_id=1000),
    ]
    album[0].invert_media = True
    album[0].effect = 456
    album[1].id = 2

    run(proc.new_album(SOURCE, album, "link"))

    assert calls == [(True, 456)]
