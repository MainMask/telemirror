"""iter_sync_directions: CHAT_MAPPING → SyncPair list, broadcast-donor handling,
channel vs forum classification."""

from config import DirectionConfig
from skylon_set import sync_pins as sp
from telemirror.messagefilters import EmptyMessageFilter

BC = -100777  # broadcast channel


def _cfg(from_t=None, to_t=None):
    return DirectionConfig(
        disable_delete=False,
        disable_edit=False,
        filters=EmptyMessageFilter(),
        from_topic_id=from_t,
        to_topic_id=to_t,
    )


def test_channel_pair_has_empty_topic_map():
    mapping = {-1001: {-9001: [_cfg()]}}
    (pair,) = sp.iter_sync_directions(mapping, BC)
    assert pair.donor_id == -1001 and pair.recipient_id == -9001
    assert pair.topic_map == {}
    assert pair.from_topics == [] and pair.to_topics == []


def test_forum_pair_topic_map():
    mapping = {-1002: {-9002: [_cfg(1, 1), _cfg(13, 3), _cfg(116, 4)]}}
    (pair,) = sp.iter_sync_directions(mapping, BC)
    assert pair.topic_map == {1: 1, 13: 3, 116: 4}
    assert pair.from_topics == [1, 13, 116]
    assert pair.to_topics == [1, 3, 4]


def test_broadcast_donor_excluded_by_default_included_with_flag():
    mapping = {BC: {-9001: [_cfg()], -9002: [_cfg()]}}
    assert sp.iter_sync_directions(mapping, BC) == []
    included = sp.iter_sync_directions(mapping, BC, include_broadcast=True)
    assert {p.recipient_id for p in included} == {-9001, -9002}


def test_broadcast_recipient_kept():
    mapping = {-1001: {BC: [_cfg()]}}
    (pair,) = sp.iter_sync_directions(mapping, BC)
    assert pair.recipient_id == BC
