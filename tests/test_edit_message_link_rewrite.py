"""Pass 22: `edit_message` must rewrite internal t.me links like `new_message`
does. Before the fix a source edit reverted the mirror's link to its own
mirror post (`t.me/c/<mirror>/500`) back to the donor's private link
(`t.me/c/<donor>/5`), and `fallback_link_url` was ignored."""

import logging
from types import SimpleNamespace

from telethon import utils
from telethon.tl import types

import telemirror.mirroring as mirroring
from config import DirectionConfig
from telemirror.messagefilters import EmptyMessageFilter
from telemirror.mirroring import EventProcessor
from telemirror.misc.links import private_message_link
from telemirror.storage import InMemoryDatabase, MirrorMessage
from tests.conftest import make_message, run

SOURCE = -1001000000000
TARGET = -1002000000001
OTHER = -1002000000002
REF_RAW = 2000000009
REF = utils.get_peer_id(types.PeerChannel(REF_RAW))
FALLBACK = "https://t.me/fallback"


def _cfg():
    return DirectionConfig(
        disable_delete=False,
        disable_edit=False,
        filters=EmptyMessageFilter(),
        fallback_link_url=FALLBACK,
    )


class _Client:
    def __init__(self):
        self.edits = []

    async def edit_message(self, entity, message, text=None, formatting_entities=None, **kw):
        self.edits.append(
            (entity, [getattr(e, "url", None) for e in formatting_entities or []])
        )


def _msg():
    m = make_message(
        "link",
        entities=[
            types.MessageEntityTextUrl(
                offset=0, length=4, url=f"https://t.me/c/{REF_RAW}/5"
            )
        ],
    )
    m.id = 7
    m._chat = SimpleNamespace(noforwards=False)
    return m


def _processor(db, client, mapping):
    return EventProcessor(
        chat_mapping=mapping,
        database=db,
        client=client,
        logger=logging.getLogger("test.editlinks"),
    )


def test_edit_keeps_the_rewritten_mirror_link(monkeypatch):
    sent = []

    async def fake_send_message(client, entity, message, formatting_entities=None, **kw):
        sent.append([getattr(e, "url", None) for e in formatting_entities or []])
        return types.Message(id=900, peer_id=types.PeerChannel(1), message="x")

    monkeypatch.setattr(mirroring, "send_message", fake_send_message)

    db = run(InMemoryDatabase())
    run(db.insert(MirrorMessage(5, REF, 500, TARGET)))
    client = _Client()
    proc = _processor(db, client, {SOURCE: {TARGET: [_cfg()]}, REF: {TARGET: [_cfg()]}})

    run(proc.new_message(SOURCE, _msg(), "link"))
    run(proc.edit_message(SOURCE, _msg(), "link"))

    mirror_link = private_message_link(TARGET, 500)
    assert sent == [[mirror_link]]
    assert client.edits == [(TARGET, [mirror_link])]


def test_edit_uses_fallback_when_target_has_no_mirror_of_the_referenced_post():
    db = run(InMemoryDatabase())
    run(db.insert(MirrorMessage(5, REF, 500, OTHER)))  # referenced post lives elsewhere
    run(db.insert(MirrorMessage(7, SOURCE, 900, TARGET)))
    client = _Client()
    proc = _processor(db, client, {SOURCE: {TARGET: [_cfg()]}, REF: {OTHER: [_cfg()]}})

    run(proc.edit_message(SOURCE, _msg(), "link"))

    assert client.edits == [(TARGET, [FALLBACK])]


def test_link_lookup_failure_skips_only_that_mirror():
    class _FlakyDB(InMemoryDatabase):
        failed = False

        async def get_messages(self, original_id, original_channel):
            if original_channel == REF and not self.failed:
                self.failed = True
                raise RuntimeError("db down")
            return await super().get_messages(original_id, original_channel)

    db = run(_FlakyDB())
    run(db.insert_batch([
        MirrorMessage(7, SOURCE, 900, TARGET),
        MirrorMessage(7, SOURCE, 901, OTHER),
    ]))
    client = _Client()
    proc = _processor(
        db, client, {SOURCE: {TARGET: [_cfg()], OTHER: [_cfg()]}, REF: {TARGET: [_cfg()]}}
    )

    # The first mirror's lookup fails: it is logged and skipped, and the
    # second mirror is still edited instead of the whole edit aborting.
    run(proc.edit_message(SOURCE, _msg(), "link"))

    assert client.edits == [(OTHER, [FALLBACK])]
