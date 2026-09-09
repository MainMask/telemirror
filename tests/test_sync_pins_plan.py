"""Pure helpers: build_pin_map, plan_pin_actions, _get_msg_topic."""

import logging

from skylon_set import sync_pins as sp
from telemirror.storage import MirrorMessage

_LOG = logging.getLogger("test.sync_pins")
S, T = -1001, -9001


# --- build_pin_map -------------------------------------------------------

def test_build_pin_map_basic():
    rows = [MirrorMessage(10, S, 910, T), MirrorMessage(7, S, 907, T)]
    assert sp.build_pin_map(rows) == ({10: 910, 7: 907}, [])


def test_build_pin_map_duplicate_keeps_smallest():
    rows = [MirrorMessage(10, S, 911, T), MirrorMessage(10, S, 910, T)]
    assert sp.build_pin_map(rows) == ({10: 910}, [10])


# --- plan_pin_actions --------------------------------------------------

def test_plan_noop_when_already_pinned():
    plan = sp.plan_pin_actions([910, 907], {907, 910}, {907, 910}, reconcile=True)
    assert plan.to_pin == [] and plan.to_unpin == []


def test_plan_pins_missing_ascending():
    plan = sp.plan_pin_actions([910, 907, 905], {910}, {910}, reconcile=True)
    assert plan.to_pin == [905, 907] and plan.to_unpin == []


def test_plan_reconcile_unpins_stale_managed():
    plan = sp.plan_pin_actions([910], {910, 800}, {910, 800}, reconcile=True)
    assert plan.to_unpin == [800]


def test_plan_reconcile_keeps_manual_pin():
    # 555 is pinned but not managed by the mirror -> untouched
    plan = sp.plan_pin_actions([910], {910, 555}, {910}, reconcile=True)
    assert plan.to_unpin == []


def test_plan_additive_never_unpins():
    plan = sp.plan_pin_actions([910], {910, 800}, {910, 800}, reconcile=False)
    assert plan.to_unpin == []


def test_plan_empty_donor_guard():
    kept = sp.plan_pin_actions([], {800}, {800}, reconcile=True, allow_clear=False)
    assert kept.to_unpin == []
    cleared = sp.plan_pin_actions([], {800}, {800}, reconcile=True, allow_clear=True)
    assert cleared.to_unpin == [800]


# --- resolve_desired_pins -------------------------------------------------

class _DonorMsg:
    def __init__(self, mid, chat_id=S):
        self.id = mid
        self.chat_id = chat_id


def test_resolve_desired_pins_skips_unmapped():
    pins = [_DonorMsg(9), _DonorMsg(42), _DonorMsg(5)]
    desired, skipped = sp.resolve_desired_pins(pins, {9: 909, 5: 905}, _LOG, "lbl")
    assert desired == [909, 905] and skipped == 1
