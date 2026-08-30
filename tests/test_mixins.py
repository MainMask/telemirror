from types import SimpleNamespace

from telethon.tl import types

from telemirror.mixins import MessageLink
from tests.conftest import make_message

_link = MessageLink().message_link


def test_private_channel_link_uses_marked_id():
    msg = make_message(channel_id=1000)  # peer_id = PeerChannel(1000), no _chat
    assert _link(msg) == "https://t.me/c/1000/1"


def test_public_channel_link_uses_username():
    msg = make_message(channel_id=1000)
    msg._chat = SimpleNamespace(username="mychan")
    assert _link(msg) == "https://t.me/mychan/1"


def test_private_message_returns_none():
    msg = types.Message(id=7, peer_id=types.PeerUser(123), message="")
    assert _link(msg) is None
