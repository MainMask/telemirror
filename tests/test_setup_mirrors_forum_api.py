"""Guards the telethon 1.44 forum-topic API migration. Telegram moved these three
requests from ``telethon.tl.functions.channels`` to ``.messages`` and renamed the
``channel=`` argument to ``peer=``. A wrong namespace or arg name silently breaks
channel/topic creation in the setup wizard, and there is no other test that
constructs these requests."""

from telethon.tl.functions import channels, messages

from skylon_set import _common
from skylon_set import setup_mirrors as sm


def test_forum_requests_come_from_messages_namespace():
    # GetForumTopics is issued from the shared helper, the rest from the wizard
    assert _common.GetForumTopicsRequest is messages.GetForumTopicsRequest
    assert sm.CreateForumTopicRequest is messages.CreateForumTopicRequest
    assert sm.EditForumTopicRequest is messages.EditForumTopicRequest
    # channel-scoped requests must NOT have moved
    assert sm.ToggleForumRequest is channels.ToggleForumRequest


def test_forum_requests_accept_peer_kwarg():
    get = _common.GetForumTopicsRequest(
        peer=-100, offset_date=0, offset_id=0, offset_topic=0, limit=100
    )
    assert get.peer == -100

    create = sm.CreateForumTopicRequest(peer=-100, title="t", icon_color=7)
    assert create.peer == -100 and create.title == "t"
    assert create.random_id is not None  # telethon fills it when omitted

    edit = sm.EditForumTopicRequest(peer=-100, topic_id=1, title="x")
    assert edit.peer == -100 and edit.topic_id == 1
