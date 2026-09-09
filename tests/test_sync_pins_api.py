"""Guards the telethon pinned-message API used by skylon_set/sync_pins.py:
``SearchRequest`` / ``UpdatePinnedMessageRequest`` live in the ``messages``
namespace (not ``channels``), and ``InputMessagesFilterPinned`` in ``tl.types``.
A wrong namespace or arg name silently breaks pin sync and nothing else covers it.
"""

from telethon.tl import types
from telethon.tl.functions import channels, messages

from skylon_set import sync_pins as sp


def test_pin_requests_come_from_messages_namespace():
    assert sp.SearchRequest is messages.SearchRequest
    assert sp.UpdatePinnedMessageRequest is messages.UpdatePinnedMessageRequest
    assert sp.InputMessagesFilterPinned is types.InputMessagesFilterPinned
    assert not hasattr(channels, "UpdatePinnedMessageRequest")


def test_search_request_accepts_top_msg_id():
    req = sp.SearchRequest(
        peer=-100,
        q="",
        filter=sp.InputMessagesFilterPinned(),
        min_date=None,
        max_date=None,
        offset_id=0,
        add_offset=0,
        limit=10,
        max_id=0,
        min_id=0,
        hash=0,
        top_msg_id=640,
    )
    assert req.peer == -100
    assert req.top_msg_id == 640
    assert isinstance(req.filter, sp.InputMessagesFilterPinned)


def test_update_pinned_message_request_kwargs():
    pin = sp.UpdatePinnedMessageRequest(peer=-100, id=5, silent=True)
    assert pin.id == 5 and pin.silent is True and pin.unpin is None

    unpin = sp.UpdatePinnedMessageRequest(peer=-100, id=5, unpin=True, silent=True)
    assert unpin.unpin is True
