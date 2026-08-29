from telethon.tl import types

from telemirror.mixins import UpdateEntitiesParams

upd = UpdateEntitiesParams().update_entities_params


def ent(offset, length):
    return types.MessageEntityBold(offset=offset, length=length)


def test_noop_when_diff_zero():
    e = ent(5, 3)
    upd([e], 0, 2, 0)
    assert (e.offset, e.length) == (5, 3)


def test_entity_after_replacement_shifts_offset():
    e = ent(10, 4)  # replacement in [0,3), grows by +5
    upd([e], 0, 3, 5)
    assert (e.offset, e.length) == (15, 4)


def test_entity_after_replacement_shifts_offset_negative():
    e = ent(10, 4)  # replacement in [0,3), shrinks by -2
    upd([e], 0, 3, -2)
    assert (e.offset, e.length) == (8, 4)


def test_entity_enclosing_replacement_grows_length():
    e = ent(0, 20)  # replacement fully inside entity, +5
    upd([e], 5, 8, 5)
    assert (e.offset, e.length) == (0, 25)


def test_entity_before_replacement_untouched():
    e = ent(0, 3)  # replacement starts after the entity ends
    upd([e], 10, 12, 4)
    assert (e.offset, e.length) == (0, 3)
