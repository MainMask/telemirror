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


def test_entity_head_partially_replaced_keeps_tail():
    # text "AAABBBCCC"; replace [0,6) with "X" (diff=-5) -> "XCCC"
    # bold [3,9) "BBBCCC" -> tail "CCC" only
    e = ent(3, 6)
    upd([e], 0, 6, -5)
    assert (e.offset, e.length) == (1, 3)
    assert e.offset >= 0 and e.offset + e.length <= len("XCCC")


def test_entity_tail_partially_replaced_keeps_head():
    # text "AAABBBCCC"; replace [3,9) with "Y" (diff=-5) -> "AAAY"
    # bold [0,6) "AAABBB" -> head "AAA" only
    e = ent(0, 6)
    upd([e], 3, 9, -5)
    assert (e.offset, e.length) == (0, 3)
    assert e.offset >= 0 and e.offset + e.length <= len("AAAY")


def test_entity_fully_inside_replacement_covers_placeholder():
    # text "AAABBBCCC"; replace [3,6) "BBB" with "ZZ" (diff=-1) -> "AAAZZCCC"
    # bold [3,6) -> now covers "ZZ" [3,5)
    e = ent(3, 3)
    upd([e], 3, 6, -1)
    assert (e.offset, e.length) == (3, 2)
    assert e.offset >= 0 and e.offset + e.length <= len("AAAZZCCC")
