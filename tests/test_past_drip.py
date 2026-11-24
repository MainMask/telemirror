"""History at a drip's pace (``past_mode.drip``): copied by the live mirror,
one post every ``minutes*60/posts`` seconds, waiting only after a post it sent."""

import asyncio
import logging

import pytest

from telemirror import past as past_mode
from telemirror.config import build_past_mode
from telemirror.directions import PastModeConfig
from telemirror.messagefilters import MediaDownloadError
from telemirror.mirroring import Mirroring
from telemirror.storage import InMemoryDatabase, MirrorMessage
from tests.conftest import run
from tests.test_mirror_shutdown import _Client as _ShutdownClient
from tests.test_past_mode import SRC, TGT, FakeClient, _cfg, _msg

_LOG = logging.getLogger("test.past_drip")


# --- config ------------------------------------------------------------------

def test_drip_is_seconds_between_posts():
    pm = build_past_mode({"last_n": 10, "drip": {"posts": 5, "minutes": 45}})
    assert pm.drip_interval == 540
    assert build_past_mode({"last_n": 10}).drip_interval is None
    assert build_past_mode({"last_n": 10, "drip": {"seconds": 30}}).drip_interval == 30


@pytest.mark.parametrize("drip", [
    {"posts": 0, "minutes": 45}, {"posts": 2.5, "minutes": 45}, {"posts": True, "minutes": 45},
    {"posts": 5, "minutes": 0}, {"posts": 5, "minutes": "45"}, {"posts": 5}, "5/45",
    {"posts": 5, "minutes": float("inf")}, {"posts": 5, "minutes": float("nan")},
    {"seconds": 0}, {"seconds": "30"}, {"seconds": True}, {"seconds": float("inf")},
    {"seconds": 30, "posts": 5},
])
def test_a_bad_drip_fails_the_config(drip):
    with pytest.raises(ValueError, match="drip"):
        build_past_mode({"last_n": 10, "drip": drip})


# --- the pace ----------------------------------------------------------------

class _DripClient(FakeClient):
    """``FakeClient`` + ``max_id``; ``arrive`` comes in once the pass has
    looked up the newest message (the live mirror's from then on)."""

    def __init__(self, messages, arrive=()):
        super().__init__(messages)
        self._arrive = list(arrive)

    async def get_messages(self, entity, limit=None, offset_date=None, **kw):
        got = await super().get_messages(entity, limit=limit, offset_date=offset_date, **kw)
        if limit == 1 and self._arrive:
            self._messages += self._arrive
            self._arrive = []
        return got

    def iter_messages(self, entity, limit=None, reverse=False, min_id=None, max_id=0, **kw):
        kept = [m for m in self._messages if not max_id or m.id < max_id]
        return FakeClient(kept).iter_messages(entity, limit=limit, reverse=reverse, min_id=min_id)


def _replay(monkeypatch, client, pm, db=None, discard=(), turns=None):
    """The replay with a processor that mirrors what the DB doesn't hold yet
    (and not ``discard``: a filter's); returns (sent, sleeps, db)."""
    db = db or run(InMemoryDatabase())
    sent, sleeps = [], []

    class Proc:
        def __init__(self, **kw):
            pass

        async def _send(self, ids):
            fresh = [i for i in ids if i not in discard and not await db.get_messages(i, SRC)]
            if fresh:
                await db.insert_batch([MirrorMessage(i, SRC, i + 900, TGT) for i in fresh])
                sent.append(tuple(ids))

        async def new_message(self, chat, msg, link):
            await self._send([msg.id])

        async def new_album(self, chat, album, link):
            await self._send([m.id for m in album])

    async def sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(past_mode, "EventProcessor", Proc)
    monkeypatch.setattr(past_mode.asyncio, "sleep", sleep)
    max_id = 0
    if pm.drip_interval is not None:  # as drip_history fixes it at the mirror's start
        newest = run(client.get_messages(SRC, limit=1))
        max_id = newest[0].id + 1 if newest else 1
    result = run(past_mode._replay_direction(client, db, SRC, TGT, [_cfg(pm)], _LOG, max_id=max_id,
                                             turns=turns))
    return result, sent, sleeps, db


def _drip(**kw):
    return PastModeConfig(drip_interval=540, **kw)


def test_a_drip_waits_after_each_sent_post_and_an_album_counts_once(monkeypatch):
    msgs = [_msg(1), _msg(2, grouped_id=7), _msg(3, grouped_id=7), _msg(4)]
    result, sent, sleeps, db = _replay(monkeypatch, _DripClient(msgs), _drip(full_history=True))
    assert sent == [(1,), (2, 3), (4,)]
    # not after the last: no other pair waits for it
    assert len(sleeps) == 2 and all(530 < s <= 540 for s in sleeps)
    assert result == 3  # a drip's pass returns what it sent
    assert run(db.get_past_mode_checkpoint(SRC, TGT)) == 4


def test_what_a_drip_does_not_send_costs_no_time(monkeypatch):
    """Already mirrored (the live mirror, an earlier run) or filtered out: no wait."""
    db = run(InMemoryDatabase())
    run(db.insert_batch([MirrorMessage(2, SRC, 902, TGT)]))
    msgs = [_msg(i) for i in range(1, 6)]
    result, sent, sleeps, _ = _replay(monkeypatch, _DripClient(msgs), _drip(full_history=True), db=db,
                                      discard={4})
    assert sent == [(1,), (3,), (5,)]
    assert len(sleeps) == 2
    assert result == 3


def test_a_drip_leaves_what_comes_after_its_start_to_the_live_mirror(monkeypatch, caplog):
    msgs = [_msg(i) for i in range(1, 4)]
    client = _DripClient(msgs, arrive=[_msg(4), _msg(5)])
    with caplog.at_level(logging.INFO):
        _, sent, _, db = _replay(monkeypatch, client, _drip(full_history=True))
    assert sent == [(1,), (2,), (3,)]
    assert "gone through 3/3," in caplog.text  # not /5: the live mirror's posts aren't the drip's
    assert run(db.get_past_mode_checkpoint(SRC, TGT)) == 3


def test_a_drip_last_n_stops_at_its_start_too(monkeypatch):
    msgs = [_msg(i) for i in range(1, 6)]
    client = _DripClient(msgs, arrive=[_msg(6)])
    _, sent, _, _ = _replay(monkeypatch, client, _drip(last_n=2))
    assert sent == [(4,), (5,)]


def test_without_a_drip_the_pause_is_send_delay_as_before(monkeypatch):
    msgs = [_msg(1), _msg(2)]
    result, _, sleeps, _ = _replay(monkeypatch, _DripClient(msgs), PastModeConfig(full_history=True, send_delay=1.5))
    assert sleeps == [1.5, 1.5]
    assert result == 2


def test_a_drip_sends_a_post_as_it_is_after_its_wait(monkeypatch):
    """Regression: fetched 100 at a time, a drip's posts went out as they were
    hours before — an edit or a delete meanwhile found no mirror for the live
    mirror to change, and the copy kept the old text or a deleted post."""
    client = _DripClient([_msg(1), _msg(2), _msg(3)])
    texts = []

    class Proc:
        def __init__(self, **kw):
            pass

        async def new_message(self, chat, msg, link):
            texts.append(msg.message)

    async def sleep(seconds):  # meanwhile, in the source: 2 edited, 3 deleted
        edited = _msg(2)
        edited.message = "edited"
        client._messages = [_msg(1), edited]

    monkeypatch.setattr(past_mode, "EventProcessor", Proc)
    monkeypatch.setattr(past_mode.asyncio, "sleep", sleep)
    db = run(InMemoryDatabase())

    async def mirrors_grow(ids, chat):  # each new_message counts as a post sent
        return [MirrorMessage(i, chat, i, TGT) for i in ids if len(texts) >= i]

    monkeypatch.setattr(db, "get_messages_batch", mirrors_grow)
    run(past_mode._replay_direction(client, db, SRC, TGT, [_cfg(_drip(full_history=True))], _LOG, max_id=4))
    assert texts == ["m1", "edited"]


# --- who copies which history ------------------------------------------------

def test_drip_directions_are_the_live_mirrors_the_rest_the_units():
    drip, now = _cfg(_drip(full_history=True)), _cfg(PastModeConfig(full_history=True))
    plain = _cfg(None)
    mapping = {SRC: {TGT: [now, drip, plain]}, -1003: {TGT: [now]}}
    # Regression: a pair's topics with and without a pace went both ways at
    # once, over the pair's one checkpoint — each pass skipping the other's
    # posts for good. The whole pair is the drip's, its pace first.
    assert past_mode.history_pairs(mapping, drip=True) == {(SRC, TGT): [drip, now]}
    assert past_mode.history_pairs(mapping, drip=False) == {(-1003, TGT): [now]}


def test_the_unit_skips_a_project_whose_history_all_drips(monkeypatch, caplog):
    monkeypatch.setattr(past_mode, "CHAT_MAPPING", {SRC: {TGT: [_cfg(_drip(full_history=True))]}})

    async def no_db(*a, **kw):
        raise AssertionError("nothing to replay: no DB, no sign-in")

    monkeypatch.setattr(past_mode, "open_database", no_db)
    with caplog.at_level(logging.WARNING):
        run(past_mode._run(_LOG))
    assert "the live mirror copies it" in caplog.text


# --- the live mirror's task --------------------------------------------------

_NO_POSTS = FakeClient([])  # the drip's bound looked up; _replay_with_retry stubbed


def _drip_mapping(monkeypatch, mapping=None):
    monkeypatch.setattr(past_mode, "CHAT_MAPPING",
                        mapping or {SRC: {TGT: [_cfg(_drip(full_history=True))]}})
    told, replayed = [], []

    async def notify(logger):
        told.append(True)

    async def links(*a, **kw):
        return True

    monkeypatch.setattr(past_mode, "_notify_done", notify)
    monkeypatch.setattr(past_mode, "_edit_links_pass", links)
    return told, replayed


def _replays(monkeypatch, replayed, sent=1):
    async def replay(client, db, src, tgt, cfgs, logger, **kw):
        replayed.append((src, logger.name))
        return sent

    monkeypatch.setattr(past_mode, "_replay_with_retry", replay)


def test_a_finished_history_isnt_gone_through_again(monkeypatch):
    """Regression: each restart of the mirror (nightly at least) went through
    the pair again — picking up the live mirror's not-copied posts, out of
    order, though they're in «❗ Не скопировано» already."""
    told, replayed = _drip_mapping(monkeypatch)
    _replays(monkeypatch, replayed)
    db = run(InMemoryDatabase())
    run(past_mode.drip_history(_NO_POSTS, db, _LOG))
    assert replayed == [(SRC, past_mode.DRIP_LOGGER)]  # its own logger: not the admins'
    assert told == [True]
    assert run(db.get_drip_state(SRC, TGT)) == (None, "full_history")
    run(past_mode.drip_history(_NO_POSTS, db, _LOG))  # a restart after it's done
    assert len(replayed) == 1 and told == [True]


def test_a_history_copied_later_fixes_the_finished_pairs_links_too(monkeypatch):
    """Regression: a pair's links were fixed once, when it finished — a pair
    copied later (it had given up, a direction added) left the finished one's
    links to its posts unfixed for good. Once every pair's copied, all are."""
    other = -1003333333333
    _drip_mapping(monkeypatch, {
        SRC: {TGT: [_cfg(_drip(full_history=True))]},
        other: {TGT: [_cfg(_drip(full_history=True))]},
    })
    replayed, fixed = [], []
    _replays(monkeypatch, replayed)

    async def links(client, db, pairs, logger, **kw):
        fixed.extend(pairs)
        return True

    monkeypatch.setattr(past_mode, "_edit_links_pass", links)
    db = run(InMemoryDatabase())
    run(db.set_drip_done(SRC, TGT, "full_history"))  # finished before `other` was added
    run(past_mode.drip_history(_NO_POSTS, db, _LOG))
    assert [src for src, _ in replayed] == [other]  # not copied again…
    assert sorted(fixed) == sorted([(SRC, TGT), (other, TGT)])  # …its links fixed again
    assert run(db.get_drip_state(SRC, TGT))[1] == run(db.get_drip_state(other, TGT))[1] == "full_history"


def test_another_history_or_a_cleared_target_is_copied_again(monkeypatch):
    told, replayed = _drip_mapping(monkeypatch)
    _replays(monkeypatch, replayed)
    db = run(InMemoryDatabase())
    run(db.set_drip_done(SRC, TGT, "full_history"))
    monkeypatch.setattr(past_mode, "CHAT_MAPPING", {SRC: {TGT: [_cfg(_drip(last_n=50))]}})
    run(past_mode.drip_history(_NO_POSTS, db, _LOG))  # 📜 Что копировать changed
    assert len(replayed) == 1
    assert run(db.get_drip_state(SRC, TGT))[1] == "last_n=50"
    run(db.delete_past_mode_checkpoint(SRC, TGT))  # clear_channels wiped the target
    assert run(db.get_drip_state(SRC, TGT)) == (None, None)
    run(past_mode.drip_history(_NO_POSTS, db, _LOG))
    assert len(replayed) == 2


def test_nothing_sent_tells_nobody(monkeypatch):
    told, replayed = _drip_mapping(monkeypatch)
    _replays(monkeypatch, replayed, sent=0)
    run(past_mode.drip_history(_NO_POSTS, run(InMemoryDatabase()), _LOG))
    assert replayed and told == []


def test_a_source_gone_at_the_start_stops_only_its_pairs(monkeypatch, caplog):
    """The drip's bounds are looked up at its start: a source the account lost
    mustn't stop every pair's history, start after start."""
    other = -1003333333333
    _drip_mapping(monkeypatch, {
        SRC: {TGT: [_cfg(_drip(full_history=True))]},
        other: {TGT: [_cfg(_drip(full_history=True))]},
    })
    replayed = []
    _replays(monkeypatch, replayed)

    class Client(FakeClient):
        async def get_messages(self, entity, **kw):
            if entity == SRC:
                raise RuntimeError("channel private")
            return await super().get_messages(entity, **kw)

    fixed = []

    async def links(client, db, pairs, logger, **kw):
        fixed.extend(pairs)
        return True

    monkeypatch.setattr(past_mode, "_edit_links_pass", links)
    db = run(InMemoryDatabase())
    with caplog.at_level(logging.ERROR):
        run(past_mode.drip_history(Client([]), db, _LOG))
    assert [src for src, _ in replayed] == [other]
    assert "channel private" in caplog.text
    assert run(db.get_drip_state(other, TGT))[1] == "full_history"
    # Regression: while SRC kept failing, `other`'s links were fixed again every start
    run(past_mode.drip_history(Client([]), db, _LOG))
    assert fixed == [(other, TGT)]


def test_a_floodwait_looking_up_the_bound_is_waited_out(monkeypatch):
    """Regression: it made the source's pairs give up till the next restart."""
    from telethon import errors
    _drip_mapping(monkeypatch)
    replayed = []
    _replays(monkeypatch, replayed)
    waits = []

    class Client(FakeClient):
        async def get_messages(self, entity, **kw):
            if not waits:
                raise errors.FloodWaitError(request=None, capture=600)
            return await super().get_messages(entity, **kw)

    async def sleep(seconds):
        waits.append(seconds)

    monkeypatch.setattr(past_mode.asyncio, "sleep", sleep)
    run(past_mode.drip_history(Client([]), run(InMemoryDatabase()), _LOG))
    assert waits == [600] and [src for src, _ in replayed] == [SRC]


@pytest.mark.parametrize("fails, copied", [(2, True), (past_mode._TRANSIENT_RETRY_LIMIT + 1, False)])
def test_a_network_blip_looking_up_the_bound_is_retried(monkeypatch, caplog, fails, copied):
    """Regression: a blip at the mirror's start stopped the source's pairs till
    the next start (04:00). A longer outage still gives up — the watchdog's."""
    _drip_mapping(monkeypatch)
    replayed = []
    _replays(monkeypatch, replayed)
    waits = []

    class Client(FakeClient):
        async def get_messages(self, entity, **kw):
            if len(waits) < fails:
                raise ConnectionError("Cannot send requests while disconnected")
            return await super().get_messages(entity, **kw)

    async def sleep(seconds):
        waits.append(seconds)

    monkeypatch.setattr(past_mode.asyncio, "sleep", sleep)
    with caplog.at_level(logging.ERROR):
        run(past_mode.drip_history(Client([]), run(InMemoryDatabase()), _LOG))
    assert waits == [past_mode._TRANSIENT_RETRY_WAIT] * min(fails, past_mode._TRANSIENT_RETRY_LIMIT)
    assert bool(replayed) is copied
    assert ("gave up copying its history" in caplog.text) is not copied


def test_a_pair_given_up_takes_no_turns_in_the_estimate(monkeypatch, caplog):
    other = -1003333333333
    _drip_mapping(monkeypatch, {
        SRC: {TGT: [_cfg(_drip(full_history=True))]},
        other: {TGT: [_cfg(_drip(full_history=True))]},
    })

    class Client(_DripClient):
        async def get_messages(self, entity, **kw):
            if entity == SRC:
                raise RuntimeError("channel private")
            return await super().get_messages(entity, **kw)

    class Proc:
        def __init__(self, **kw):
            pass

        async def new_message(self, chat, msg, link):
            pass

    async def sleep(seconds):
        pass

    monkeypatch.setattr(past_mode, "EventProcessor", Proc)
    monkeypatch.setattr(past_mode.asyncio, "sleep", sleep)
    with caplog.at_level(logging.INFO, logger=past_mode.DRIP_LOGGER):
        run(past_mode.drip_history(Client([_msg(1)]), run(InMemoryDatabase()), _LOG))
    assert "at most ≈9min (one post every 9min, albums count once)" in caplog.text


def test_a_pair_that_gives_up_leaves_the_others_and_the_mirror_running(monkeypatch, caplog):
    other = -1003333333333
    told, _ = _drip_mapping(monkeypatch, {
        SRC: {TGT: [_cfg(_drip(full_history=True))]},
        other: {TGT: [_cfg(_drip(full_history=True))]},
    })
    finished = []

    async def replay(client, db, src, tgt, cfgs, logger, **kw):
        if src == SRC:
            raise RuntimeError("flood for good")
        finished.append(src)
        logger.info(f"[PastMode] {src}→{tgt}: done")
        return 1

    monkeypatch.setattr(past_mode, "_replay_with_retry", replay)
    db = run(InMemoryDatabase())
    with caplog.at_level(logging.INFO):
        run(past_mode.drip_history(_NO_POSTS, db, _LOG))  # doesn't raise
    assert "the live mirror goes on" in caplog.text and "flood for good" in caplog.text
    # Regression: the run's last line was the other pair's — the panel kept saying «копируется»
    assert past_mode.DRIP_STOPPED in caplog.records[-1].getMessage()
    assert finished == [other]
    assert told == []  # not «done»: one pair stopped short
    assert run(db.get_drip_state(SRC, TGT))[1] is None  # tried again next start
    assert "links not fixed" not in caplog.text  # the other pair's were: no false alarm
    # done: its links to the posts the given-up pair copies later are fixed then (`finished`)
    assert run(db.get_drip_state(other, TGT))[1] == "full_history"


def test_the_pairs_take_turns_at_the_projects_one_pace(monkeypatch, caplog):
    """Regression: every pair ran at its own pace at once — 29 sources into one
    channel sent it 29 old posts per interval, 199 pairs flooded the account.
    Then one after another — the first channel's whole history before the
    next one's first post. Now a post from each in turn, one per interval;
    what a pair skips (already there) costs no time and no turn."""
    other = -1003333333333
    _drip_mapping(monkeypatch, {
        SRC: {TGT: [_cfg(_drip(full_history=True))]},
        other: {TGT: [_cfg(_drip(full_history=True))]},
    })
    db = run(InMemoryDatabase())
    run(db.insert_batch([MirrorMessage(1, other, 901, TGT)]))  # the live mirror's already
    events = []

    class Proc:
        def __init__(self, **kw):
            pass

        async def new_message(self, chat, msg, link):
            if not await db.get_messages(msg.id, chat):
                await db.insert_batch([MirrorMessage(msg.id, chat, msg.id + 900, TGT)])
                events.append((chat, msg.id))

    real_sleep = asyncio.sleep

    async def sleep(seconds):
        events.append("wait")
        await real_sleep(0)  # the other pairs get to run here, the turn still held

    monkeypatch.setattr(past_mode, "EventProcessor", Proc)
    monkeypatch.setattr(past_mode.asyncio, "sleep", sleep)
    with caplog.at_level(logging.INFO, logger=past_mode.DRIP_LOGGER):
        run(past_mode.drip_history(_DripClient([_msg(i) for i in (1, 2, 3)]), db, _LOG))
    # its estimate counts the other pair's turns too
    assert "at most ≈54min (one post every 9min from 2 pair(s) in turn" in caplog.text
    # the last post's interval isn't waited out: no pair left to wait for it
    assert events == [(SRC, 1), "wait", (other, 2), "wait", (SRC, 2), "wait", (other, 3), "wait",
                      (SRC, 3)]


def test_a_drip_leaves_to_the_live_mirror_what_came_after_the_mirrors_start(monkeypatch):
    """Regression: each pass looked up its bound when its turn came — a post the
    live mirror was still sending (an album's wait) was sent by both."""
    other = -1003333333333
    _drip_mapping(monkeypatch, {
        SRC: {TGT: [_cfg(_drip(full_history=True))]},
        other: {TGT: [_cfg(_drip(full_history=True))]},
    })
    db = run(InMemoryDatabase())
    client = _DripClient([_msg(1)])
    sent = []

    class Proc:
        def __init__(self, **kw):
            pass

        async def new_message(self, chat, msg, link):
            if not await db.get_messages(msg.id, chat):
                await db.insert_batch([MirrorMessage(msg.id, chat, msg.id + 900, TGT)])
                sent.append((chat, msg.id))
                if len(client._messages) == 1:
                    client._messages.append(_msg(2))  # comes in meanwhile: the live mirror's

    async def sleep(seconds):
        pass

    monkeypatch.setattr(past_mode, "EventProcessor", Proc)
    monkeypatch.setattr(past_mode.asyncio, "sleep", sleep)
    run(past_mode.drip_history(client, db, _LOG))
    assert sent == [(SRC, 1), (other, 1)]


def test_a_file_telegram_wont_serve_gives_the_turn_away_meanwhile(monkeypatch):
    """Its retries wait minutes: the other pairs' posts go on meanwhile."""
    turns = past_mode._Turns(2)
    free_while_waiting = []

    async def direction(client, db, src, tgt, cfgs, logger, total=None, turns=None, max_id=0, live=None):
        await turns.take((src, tgt))
        if not free_while_waiting:
            raise MediaDownloadError("t.me/c/1/5: exhausted", message_id=5)
        return 1

    async def sleep(seconds):
        free_while_waiting.append(not turns._lock.locked())

    monkeypatch.setattr(past_mode, "_replay_direction", direction)
    monkeypatch.setattr(past_mode.asyncio, "sleep", sleep)
    run(past_mode._replay_with_retry(object(), run(InMemoryDatabase()), SRC, TGT,
                                     [_cfg(_drip(full_history=True))], _LOG, turns=turns))
    assert free_while_waiting == [True]


@pytest.mark.parametrize("fails, gives_up", [(past_mode._TRANSIENT_RETRY_LIMIT, False),
                                             (past_mode._TRANSIENT_RETRY_LIMIT + 1, True)])
def test_a_network_blip_mid_pass_is_retried_from_the_checkpoint(monkeypatch, fails, gives_up):
    """Regression: it made the pair give up till the next start (04:00), the
    live mirror running on. A longer outage still gives up — the watchdog's."""
    turns = past_mode._Turns(2)
    calls, free_while_waiting = [], []

    async def direction(client, db, src, tgt, cfgs, logger, total=None, turns=None, max_id=0, live=None):
        await turns.take((src, tgt))
        calls.append(True)
        if len(calls) <= fails:
            raise ConnectionError("Cannot send requests while disconnected")
        return 1

    async def sleep(seconds):
        free_while_waiting.append(seconds == past_mode._TRANSIENT_RETRY_WAIT and not turns._lock.locked())

    monkeypatch.setattr(past_mode, "_replay_direction", direction)
    monkeypatch.setattr(past_mode.asyncio, "sleep", sleep)
    replay = past_mode._replay_with_retry(object(), run(InMemoryDatabase()), SRC, TGT,
                                          [_cfg(_drip(full_history=True))], _LOG, turns=turns)
    if gives_up:
        with pytest.raises(ConnectionError):
            run(replay)
    else:
        assert run(replay) == 1
    assert free_while_waiting == [True] * past_mode._TRANSIENT_RETRY_LIMIT


def test_a_network_error_still_fails_the_unit(monkeypatch):
    """Not a drip: systemd restarts the unit from the checkpoint, as before."""
    async def direction(*a, **kw):
        raise ConnectionError("Cannot send requests while disconnected")

    monkeypatch.setattr(past_mode, "_replay_direction", direction)
    with pytest.raises(ConnectionError):
        run(past_mode._replay_with_retry(object(), run(InMemoryDatabase()), SRC, TGT,
                                         [_cfg(PastModeConfig(full_history=True))], _LOG))


def test_a_restart_waits_from_the_last_post_any_pair_sent(monkeypatch):
    """The pair that sent last is done; the next one mustn't post at once."""
    other = -1003333333333
    _drip_mapping(monkeypatch, {
        SRC: {TGT: [_cfg(_drip(full_history=True))]},
        other: {TGT: [_cfg(_drip(full_history=True))]},
    })
    db = run(InMemoryDatabase())
    run(db.set_drip_sent(SRC, TGT, 1000.0))
    run(db.set_drip_done(SRC, TGT, "full_history"))
    events = []

    async def replay(client, db, src, tgt, cfgs, logger, **kw):
        events.append(src)
        return 1

    async def sleep(seconds):
        events.append(seconds)

    monkeypatch.setattr(past_mode, "_replay_with_retry", replay)
    monkeypatch.setattr(past_mode.asyncio, "sleep", sleep)
    monkeypatch.setattr(past_mode.time, "time", lambda: 1200.0)  # 200 s ago, interval 540
    run(past_mode.drip_history(_NO_POSTS, db, _LOG))
    assert events == [340, other]


@pytest.mark.parametrize("links_fail", ["raises", "incomplete"])
def test_links_left_unfixed_are_fixed_next_start_without_copying_again(monkeypatch, caplog, links_fail):
    """Regression: the pairs were marked done before their links were fixed —
    that pass failing (or Telegram not giving some posts) left them for good."""
    told, replayed = _drip_mapping(monkeypatch)
    _replays(monkeypatch, replayed)
    fixed = []

    async def broken_links(client, db, pairs, logger, **kw):
        fixed.append(list(pairs))
        if links_fail == "raises":
            raise OSError("the network is down")
        return False

    monkeypatch.setattr(past_mode, "_edit_links_pass", broken_links)
    db = run(InMemoryDatabase())
    with caplog.at_level(logging.ERROR):
        run(past_mode.drip_history(_NO_POSTS, db, _LOG))
    assert past_mode.DRIP_STOPPED in caplog.text and told == []
    assert run(db.get_drip_state(SRC, TGT))[1] == "full_history, links left to fix"

    async def links(client, db, pairs, logger, **kw):
        fixed.append(list(pairs))
        return True

    monkeypatch.setattr(past_mode, "_edit_links_pass", links)
    run(past_mode.drip_history(_NO_POSTS, db, _LOG))  # the next start
    assert len(replayed) == 1  # not copied again
    assert fixed == [[(SRC, TGT)], [(SRC, TGT)]]
    assert run(db.get_drip_state(SRC, TGT))[1] == "full_history"
    assert told == [True]  # done now: not told before
    run(past_mode.drip_history(_NO_POSTS, db, _LOG))
    assert len(fixed) == 2  # and that's it


@pytest.mark.parametrize("links_fail", ["raises", "incomplete"])
def test_one_pairs_links_left_unfixed_dont_hold_back_the_others(monkeypatch, caplog, links_fail):
    """Regression: one pair whose posts Telegram didn't give (its source gone
    private) kept every pair's links pass running start after start."""
    other = -1003333333333
    told, replayed = _drip_mapping(monkeypatch, {
        SRC: {TGT: [_cfg(_drip(full_history=True))]},
        other: {TGT: [_cfg(_drip(full_history=True))]},
    })
    _replays(monkeypatch, replayed)

    async def links(client, db, pairs, logger, **kw):
        if (SRC, TGT) in pairs:
            if links_fail == "raises":
                raise RuntimeError("channel private")
            return False
        return True

    monkeypatch.setattr(past_mode, "_edit_links_pass", links)
    db = run(InMemoryDatabase())
    with caplog.at_level(logging.ERROR):
        run(past_mode.drip_history(_NO_POSTS, db, _LOG))
    assert past_mode.DRIP_STOPPED in caplog.text and str(SRC) in caplog.text and told == []
    assert run(db.get_drip_state(SRC, TGT))[1] == "full_history, links left to fix"
    assert run(db.get_drip_state(other, TGT))[1] == "full_history"


def test_a_drip_that_fails_before_its_pairs_tells_the_admins(monkeypatch, caplog):
    """Regression: the DB down at the mirror's start ended the task silently —
    no history copied, the panel still showing it as under way."""
    _drip_mapping(monkeypatch)

    class DownDB(InMemoryDatabase):
        async def get_drip_state(self, source, target):
            raise OSError("the DB is down")

    with caplog.at_level(logging.ERROR):
        run(past_mode.drip_history(_NO_POSTS, run(DownDB()), _LOG))  # doesn't raise
    assert "drip stopped, the live mirror goes on" in caplog.text and "the DB is down" in caplog.text


def test_every_run_ends_its_journal_with_done_once_all_is_copied(monkeypatch, caplog):
    """The panel tells «copied» from «under way» by this run's last line."""
    told, replayed = _drip_mapping(monkeypatch)
    _replays(monkeypatch, replayed)
    db = run(InMemoryDatabase())
    for _ in range(2):  # the run that copies it, then a restart with nothing left
        caplog.clear()
        with caplog.at_level(logging.INFO, logger=past_mode.DRIP_LOGGER):
            run(past_mode.drip_history(_NO_POSTS, db, _LOG))
        assert caplog.records[-1].getMessage() == past_mode.DRIP_DONE
    assert len(replayed) == 1


def test_the_panel_reads_the_drips_lines():
    from bot.routers import _units
    assert _units.DRIP_DONE == past_mode.DRIP_DONE
    assert _units.DRIP_STOPPED == past_mode.DRIP_STOPPED


# --- the pace across restarts ------------------------------------------------

def test_a_restart_waits_out_the_rest_of_the_interval(monkeypatch):
    """Regression: the last send was known only in memory — a restart sent the
    next post at once, and a crash loop (Restart=always, 10 s) one per restart."""
    db = run(InMemoryDatabase())
    run(db.set_drip_sent(SRC, TGT, 1000.0))
    monkeypatch.setattr(past_mode.time, "time", lambda: 1200.0)  # 200 s ago, interval 540
    _, sent, sleeps, _ = _replay(monkeypatch, _DripClient([_msg(1)]), _drip(full_history=True), db=db)
    assert sleeps[0] == 340 and sent == [(1,)]
    assert run(db.get_drip_state(SRC, TGT))[0] == 1200.0  # this send kept for the next start


@pytest.mark.parametrize("ago", [600, -5000])  # long enough / a clock set back
def test_no_wait_past_the_interval_and_never_longer(monkeypatch, ago):
    db = run(InMemoryDatabase())
    run(db.set_drip_sent(SRC, TGT, 10_000.0 - ago))
    monkeypatch.setattr(past_mode.time, "time", lambda: 10_000.0)
    _, _, sleeps, _ = _replay(monkeypatch, _DripClient([_msg(1)]), _drip(full_history=True), db=db)
    assert sleeps == ([] if ago == 600 else [540])


def test_a_restarted_last_n_drip_doesnt_count_the_live_mirrors_posts(monkeypatch):
    """Regression: the budget left was last_n minus every mirror of the pair —
    the live mirror's posts beside the drip too, so each nightly restart cut
    the history short and then marked it done."""
    db = run(InMemoryDatabase())
    run(db.insert_batch([MirrorMessage(i, SRC, i + 900, TGT) for i in (6, 7)]))  # the drip's, last_n=5: 6..10
    run(db.set_past_mode_checkpoint(SRC, TGT, 7))
    run(db.insert_batch([MirrorMessage(i, SRC, i + 900, TGT) for i in (11, 12)]))  # the live mirror's
    msgs = [_msg(i) for i in range(1, 13)]
    _, sent, _, _ = _replay(monkeypatch, _DripClient(msgs), _drip(last_n=5), db=db)
    assert sent == [(8,), (9,), (10,)]


# --- last_n isn't held in memory ---------------------------------------------

def test_last_n_streams_from_where_the_last_n_begin(monkeypatch):
    """The last N were buffered as whole messages — with a large last_n, in the
    live mirror's memory now. Only where they begin is found first."""
    msgs = [_msg(i) for i in range(1, 8)] + [_msg(8, grouped_id=3), _msg(9, grouped_id=3), _msg(10)]
    asked = []

    class Client(_DripClient):
        def iter_messages(self, entity, **kw):
            asked.append(kw)
            return super().iter_messages(entity, **kw)

    _, sent, _, _ = _replay(monkeypatch, Client(msgs), _drip(last_n=3))
    assert sent == [(8, 9), (10,)]  # the album at the boundary kept whole
    assert asked[1]["reverse"] and asked[1]["min_id"] == 7 and asked[1]["max_id"] == 11
    assert asked[2]["min_id"] == 9 and asked[2]["max_id"] == 11  # after the wait: from the checkpoint


def test_a_last_n_scan_leaves_the_turn_to_the_other_pairs(monkeypatch):
    """Regression: a large last_n's scan for where its posts begin (Telethon
    paces those requests — hours for a million) held the turn: no pair posted."""
    turns = past_mode._Turns(2)
    free_while_scanning = []

    class Client(_DripClient):
        def iter_messages(self, entity, limit=None, **kw):
            if limit is not None:  # the scan
                free_while_scanning.append(not turns._lock.locked() and turns.scan.locked())
            return super().iter_messages(entity, limit=limit, **kw)

    _, sent, _, _ = _replay(monkeypatch, Client([_msg(i) for i in (1, 2, 3)]), _drip(last_n=1), turns=turns)
    assert free_while_scanning == [True]
    assert sent == [(3,)]


def test_a_restart_waits_out_the_longest_of_hand_written_paces(monkeypatch, caplog):
    """🐢 Темп sets one for all; different ones by hand: not the first pair's
    interval, whichever it is — the longest."""
    other = -1003333333333
    _drip_mapping(monkeypatch, {
        SRC: {TGT: [_cfg(PastModeConfig(drip_interval=30, full_history=True))]},
        other: {TGT: [_cfg(_drip(full_history=True))]},
    })
    db = run(InMemoryDatabase())
    run(db.set_drip_sent(other, TGT, 1000.0))
    waits = []

    async def replay(client, db, src, tgt, cfgs, logger, **kw):
        return 0

    async def sleep(seconds):
        waits.append(seconds)

    monkeypatch.setattr(past_mode, "_replay_with_retry", replay)
    monkeypatch.setattr(past_mode.asyncio, "sleep", sleep)
    monkeypatch.setattr(past_mode.time, "time", lambda: 1200.0)  # 200 s ago
    with caplog.at_level(logging.WARNING, logger=past_mode.DRIP_LOGGER):
        run(past_mode.drip_history(_NO_POSTS, db, _LOG))
    assert waits == [340]
    assert "different paces (30s, 9min)" in caplog.text


def test_the_mirror_runs_the_history_beside_it_and_stops_it_with_itself():
    started, cancelled = asyncio.Event(), []

    async def history(client, processor):
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    mirror = Mirroring(chat_mapping={}, database=run(InMemoryDatabase()), client=object(),
                       logger=logging.getLogger("test.past_drip"), history=history)

    async def live(client):
        await started.wait()

    run(mirror._Mirroring__connect_client(_ShutdownClient(live)))
    assert cancelled == [True]
