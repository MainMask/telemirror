from telethon.tl import types

from telemirror.misc.message_groups import iter_message_groups
from tests.conftest import run


def _msg(mid, grouped_id=None):
    return types.Message(
        id=mid, peer_id=types.PeerChannel(1), message="", grouped_id=grouped_id
    )


async def _collect(items):
    async def _aiter():
        for it in items:
            yield it

    out = []
    async for group in iter_message_groups(_aiter()):
        out.append([m.id for m in group] if isinstance(group, list) else group.id)
    return out


def test_singles_and_runs():
    stream = [
        _msg(1),
        _msg(2, grouped_id=10),
        _msg(3, grouped_id=10),
        _msg(4),
        _msg(5, grouped_id=20),
        _msg(6, grouped_id=20),
        _msg(7, grouped_id=20),
    ]
    assert run(_collect(stream)) == [1, [2, 3], 4, [5, 6, 7]]


def test_single_item_album_yields_list():
    assert run(_collect([_msg(1, grouped_id=99), _msg(2)])) == [[1], 2]


def test_adjacent_different_group_ids_split():
    stream = [_msg(1, grouped_id=10), _msg(2, grouped_id=11)]
    assert run(_collect(stream)) == [[1], [2]]


def test_non_message_items_skipped():
    assert run(_collect([_msg(1), None, _msg(2)])) == [1, 2]


def test_empty_stream():
    assert run(_collect([])) == []
