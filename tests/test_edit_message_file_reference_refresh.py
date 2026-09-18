"""A stale file_reference on edit_message (FileReferenceExpiredError) must be
refreshed and retried once, same contract as new_message/new_album's
_send_with_reference_refresh — not silently dropped into the generic
error handler."""

import logging

from telethon import errors
from telethon.tl import types

from config import DirectionConfig
from telemirror.messagefilters import EmptyMessageFilter
from telemirror.mirroring import EventProcessor
from telemirror.storage import InMemoryDatabase, MirrorMessage
from tests.conftest import make_message, run

SOURCE = -1001000000000
TARGET = -1002000000001


def _doc_media(file_reference: bytes) -> types.MessageMediaDocument:
    return types.MessageMediaDocument(
        document=types.Document(
            id=42, access_hash=0, file_reference=file_reference, date=None,
            mime_type="application/pdf", size=1024, dc_id=1, attributes=[],
        )
    )


class _StaleReferenceClient:
    def __init__(self, fresh_message):
        self._fresh_message = fresh_message
        self.edit_attempts = []
        self.get_messages_calls = []

    async def edit_message(self, entity, message, file=None, **kw):
        self.edit_attempts.append(file)
        if len(self.edit_attempts) == 1:
            raise errors.FileReferenceExpiredError(request=None)

    async def get_messages(self, entity, ids):
        self.get_messages_calls.append((entity, ids))
        return self._fresh_message


def test_edit_message_refreshes_stale_file_reference_and_retries():
    db = run(InMemoryDatabase())
    run(db.insert_batch([MirrorMessage(1, SOURCE, 900, TARGET)]))

    fresh_media = _doc_media(b"fresh-reference")
    fresh_message = make_message(media=fresh_media, channel_id=1000)
    client = _StaleReferenceClient(fresh_message)

    cfg = DirectionConfig(
        disable_delete=False, disable_edit=False, filters=EmptyMessageFilter()
    )
    proc = EventProcessor(
        chat_mapping={SOURCE: {TARGET: [cfg]}},
        database=db,
        client=client,
        logger=logging.getLogger("test.editrefresh"),
    )

    msg = make_message(media=_doc_media(b"stale-reference"), channel_id=1000)
    msg.id = 1
    msg._client = client

    run(proc.edit_message(SOURCE, msg, "link"))

    # First attempt failed with the stale reference, refetched the source
    # message, and retried once with the fresh media.
    assert client.get_messages_calls == [(SOURCE, 1)]
    assert len(client.edit_attempts) == 2
    assert client.edit_attempts[0].document.file_reference == b"stale-reference"
    assert client.edit_attempts[1].document.file_reference == b"fresh-reference"


TARGET_A = -1002000000001
TARGET_B = -1002000000002


def test_edit_message_reuses_refreshed_reference_across_fan_out_targets():
    """The first target's refresh must update the shared source message so
    the second target's filtered copy is built from fresh media and never
    hits FileReferenceExpiredError itself — only one refetch total, not one
    per target."""
    db = run(InMemoryDatabase())
    run(db.insert_batch([
        MirrorMessage(1, SOURCE, 900, TARGET_A),
        MirrorMessage(1, SOURCE, 901, TARGET_B),
    ]))

    fresh_media = _doc_media(b"fresh-reference")
    fresh_message = make_message(media=fresh_media, channel_id=1000)
    client = _StaleReferenceClient(fresh_message)

    cfg_a = DirectionConfig(
        disable_delete=False, disable_edit=False, filters=EmptyMessageFilter()
    )
    cfg_b = DirectionConfig(
        disable_delete=False, disable_edit=False, filters=EmptyMessageFilter()
    )
    proc = EventProcessor(
        chat_mapping={SOURCE: {TARGET_A: [cfg_a], TARGET_B: [cfg_b]}},
        database=db,
        client=client,
        logger=logging.getLogger("test.editrefresh"),
    )

    msg = make_message(media=_doc_media(b"stale-reference"), channel_id=1000)
    msg.id = 1
    msg._client = client

    run(proc.edit_message(SOURCE, msg, "link"))

    # Only the first target's edit hit the stale reference and refetched;
    # the second target's filtered copy was already built from the refreshed
    # `message.media`, so its single edit attempt succeeds outright.
    assert client.get_messages_calls == [(SOURCE, 1)]
    assert len(client.edit_attempts) == 3
    assert client.edit_attempts[0].document.file_reference == b"stale-reference"
    assert client.edit_attempts[1].document.file_reference == b"fresh-reference"
    assert client.edit_attempts[2].document.file_reference == b"fresh-reference"


class _RefetchErrorsClient:
    async def edit_message(self, entity, message, file=None, **kw):
        raise errors.FileReferenceExpiredError(request=None)

    async def get_messages(self, entity, ids):
        raise ConnectionError("boom")


def test_edit_message_logs_refetch_failure_only_once(caplog):
    """A refetch that itself raises must log the real failure once — not
    also fall through to the unconditional (and factually wrong) 'source is
    gone' message meant for a clean None result."""
    db = run(InMemoryDatabase())
    run(db.insert_batch([MirrorMessage(1, SOURCE, 900, TARGET)]))

    client = _RefetchErrorsClient()
    cfg = DirectionConfig(
        disable_delete=False, disable_edit=False, filters=EmptyMessageFilter()
    )
    proc = EventProcessor(
        chat_mapping={SOURCE: {TARGET: [cfg]}},
        database=db,
        client=client,
        logger=logging.getLogger("test.editrefresh"),
    )

    msg = make_message(media=_doc_media(b"stale-reference"), channel_id=1000)
    msg.id = 1
    msg._client = client

    with caplog.at_level(logging.ERROR, logger="test.editrefresh"):
        run(proc.edit_message(SOURCE, msg, "link"))

    assert len(caplog.records) == 1
    assert "refetch failed" in caplog.records[0].message
    assert "boom" in caplog.records[0].message


class _AlwaysStaleClient:
    async def edit_message(self, entity, message, file=None, **kw):
        raise errors.FileReferenceExpiredError(request=None)

    async def get_messages(self, entity, ids):
        return None  # source message is gone


def test_edit_message_gives_up_when_source_message_is_gone():
    """fetch_fresh_media returning None (source gone/no media) must not raise
    — the edit is dropped for this target the same way a refetch failure
    always has been."""
    db = run(InMemoryDatabase())
    run(db.insert_batch([MirrorMessage(1, SOURCE, 900, TARGET)]))

    client = _AlwaysStaleClient()
    cfg = DirectionConfig(
        disable_delete=False, disable_edit=False, filters=EmptyMessageFilter()
    )
    proc = EventProcessor(
        chat_mapping={SOURCE: {TARGET: [cfg]}},
        database=db,
        client=client,
        logger=logging.getLogger("test.editrefresh"),
    )

    msg = make_message(media=_doc_media(b"stale-reference"), channel_id=1000)
    msg.id = 1
    msg._client = client

    run(proc.edit_message(SOURCE, msg, "link"))  # must not raise
