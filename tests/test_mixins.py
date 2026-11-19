from types import SimpleNamespace

from telethon.tl import types

from telemirror.mixins import CopyEventMessage, MessageLink
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


def test_copy_message_preserves_invert_media_and_effect():
    """Without this, `invert_media` ("media below caption" layout) and
    `effect` (message-effect id) are always dropped on copy-mode mirrors,
    regardless of the source — nothing downstream can recover them once
    lost here."""
    msg = types.Message(
        id=1, peer_id=types.PeerChannel(1000), message="x",
        invert_media=True, effect=123,
    )
    cloned = CopyEventMessage().copy_message(msg)
    assert cloned.invert_media is True
    assert cloned.effect == 123


def test_copy_message_carries_every_constructor_field():
    """Fields outside the old hand-written list (offline, video_processing_pending…)
    survive the copy; media and entities are copies, not the same objects."""
    msg = make_message("text")
    msg.offline = True
    msg.video_processing_pending = True
    msg.entities = [types.MessageEntityBold(offset=0, length=4)]
    cloned = CopyEventMessage().copy_message(msg)
    assert cloned.offline is True and cloned.video_processing_pending is True
    assert cloned.entities[0].length == 4 and cloned.entities[0] is not msg.entities[0]
