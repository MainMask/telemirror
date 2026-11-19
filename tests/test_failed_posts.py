"""Posts the live mirror couldn't copy: each fan-out's outcomes reach the sink,
the list (failed.json) and its summary notice, and the panel's requests copy
them again."""

import json
import logging
import os
import time

import pytest
from telethon import errors
from telethon.tl import types

import telemirror.mirroring as mirroring
from telemirror import failed, projects
from telemirror.directions import DirectionConfig
from telemirror.messagefilters import EmptyMessageFilter
from telemirror.messagefilters.base import FilterAction, FilterResult
from telemirror.mirroring import EventProcessor, Mirroring, NoticeLogHandler
from telemirror.outcomes import ALL_CHATS, DUPLICATE, FAILED, FILTERED, SENT, Outcomes
from telemirror.sink import LiveSink
from telemirror.storage import InMemoryDatabase, MirrorMessage
from tests.conftest import make_message, run

SOURCE = -1001000000000
T1, T2, T3 = -1002000000001, -1002000000002, -1002000000003


class _Discard:
    restricted_content_allowed = False

    async def process(self, entity, event_type):
        return FilterResult(FilterAction.DISCARD, entity)


class _Boom:
    restricted_content_allowed = False

    async def process(self, entity, event_type):
        raise RuntimeError("boom")


class _Sink:
    def __init__(self):
        self.records = []

    def record(self, chat_id, ids, link, outcomes):
        self.records.append((chat_id, ids, link, outcomes))


def _cfg(filters=None):
    return DirectionConfig(disable_delete=False, disable_edit=False, filters=filters or EmptyMessageFilter())


def _processor(mapping, sink=None, db=None):
    return EventProcessor(chat_mapping={SOURCE: mapping}, database=db or run(InMemoryDatabase()),
                          client=object(), logger=logging.getLogger("test.failed"), sink=sink)


def _sent(entity):
    return types.Message(id=500 + abs(entity) % 10, peer_id=types.PeerChannel(1), message="x")


def test_outcomes_per_target(monkeypatch):
    async def send(client, entity, message, **kw):
        if entity == T3:
            raise errors.ChatWriteForbiddenError(request=None)
        return _sent(entity)

    monkeypatch.setattr(mirroring, "send_message", send)
    sink = _Sink()
    proc = _processor({T1: [_cfg()], T2: [_cfg(_Discard())], T3: [_cfg()]}, sink)
    run(proc.new_message(SOURCE, make_message("hello"), "link"))

    (chat, ids, link, outcomes), = sink.records
    assert (chat, ids, link) == (SOURCE, [1], "link")
    assert [(t.chat, t.state) for t in outcomes.targets] == [(T1, SENT), (T2, FILTERED), (T3, FAILED)]
    assert "ChatWriteForbiddenError" in outcomes.failed[0].reason


def test_filter_bug_is_a_failure_with_its_reason(monkeypatch):
    monkeypatch.setattr(mirroring, "send_message", lambda client, entity, message, **kw: _async(_sent(entity)))
    sink = _Sink()
    run(_processor({T1: [_cfg(_Boom())], T2: [_cfg()]}, sink).new_message(SOURCE, make_message("x"), "l"))
    outcomes = sink.records[0][3]
    assert [(t.chat, t.state) for t in outcomes.targets] == [(T1, FAILED), (T2, SENT)]
    assert outcomes.failed[0].reason == "сбой фильтра: RuntimeError: boom"


async def _async(value):
    return value


def test_floodwait_mid_fanout_fails_the_rest_and_propagates(monkeypatch):
    async def send(client, entity, message, **kw):
        if entity == T2:
            raise errors.FloodWaitError(request=None)
        return _sent(entity)

    monkeypatch.setattr(mirroring, "send_message", send)
    sink = _Sink()
    proc = _processor({T1: [_cfg()], T2: [_cfg()], T3: [_cfg()]}, sink)
    with pytest.raises(errors.FloodWaitError):
        run(proc.new_message(SOURCE, make_message("x"), "l"))
    outcomes = sink.records[0][3]
    assert [(t.chat, t.state) for t in outcomes.targets] == [(T1, SENT), (T2, FAILED)]
    assert outcomes.failed[0].reason.startswith("FloodWaitError")


def test_broken_off_before_any_target_is_one_failure_for_all():
    class _BadDB(InMemoryDatabase):
        async def get_messages(self, *a, **kw):
            raise RuntimeError("db down")

    sink = _Sink()
    run(_processor({T1: [_cfg()]}, sink, run(_BadDB())).new_message(SOURCE, make_message("x"), "l"))
    outcomes = sink.records[0][3]
    assert [(t.chat, t.state, t.reason) for t in outcomes.targets] == [(ALL_CHATS, FAILED, "RuntimeError: db down")]


def test_album_outcomes(monkeypatch):
    async def send_file(client, entity, caption, file, **kw):
        if entity == T2:
            raise RuntimeError("nope")
        return [_sent(entity)]

    monkeypatch.setattr(mirroring, "send_file", send_file)
    sink = _Sink()
    album = [make_message("a", media=types.MessageMediaUnsupported())]
    run(_processor({T1: [_cfg()], T2: [_cfg()]}, sink).new_album(SOURCE, album, "l"))
    assert [(t.chat, t.state) for t in sink.records[0][3].targets] == [(T1, SENT), (T2, FAILED)]


def test_send_failure_log_is_not_a_notice_with_a_sink(monkeypatch, caplog):
    async def send(client, entity, message, **kw):
        raise RuntimeError("nope")

    monkeypatch.setattr(mirroring, "send_message", send)
    with caplog.at_level(logging.ERROR, logger="test.failed"):
        run(_processor({T1: [_cfg()]}, _Sink()).new_message(SOURCE, make_message("x"), "l"))
        run(_processor({T1: [_cfg()]}).new_message(SOURCE, make_message("x"), "l"))
    with_sink, without = (r for r in caplog.records if "Error while sending" in r.getMessage())
    assert with_sink.notice is False and without.notice is True

    sent = []

    class _Loop:
        def call_soon_threadsafe(self, fn, *args):
            sent.append(args)

    handler = NoticeLogHandler(notifier=None, loop=_Loop())  # type: ignore[arg-type]
    handler.emit(with_sink)
    handler.emit(without)
    assert len(sent) == 1


# ── the list ─────────────────────────────────────────────────────────────────

@pytest.fixture
def project_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path)
    (tmp_path / "p").mkdir()
    return tmp_path / "p"


def _target(chat, reason="why"):
    from telemirror.outcomes import Target
    return Target(chat, None, FAILED, reason)


def test_queue_upsert_remove_and_flush(project_dir):
    q = failed.FailedQueue("p")
    q.upsert(SOURCE, [7], "l7", [_target(T1)])
    q.upsert(SOURCE, [8, 9], "l8", [_target(T2)])
    q.upsert(SOURCE, [7], "l7", [_target(T3)])  # failed again: replaced, moved to the end
    q.flush()
    entries = failed.load("p")
    assert [e["link"] for e in entries] == ["l8", "l7"]
    assert entries[1]["targets"] == [{"chat": T3, "topic": None, "reason": "why"}]
    assert entries[1]["id"] == failed.entry_id(SOURCE, 7)

    q.remove(SOURCE, 8)
    q.flush()
    assert [e["link"] for e in failed.load("p")] == ["l7"]
    assert [e["link"] for e in failed.FailedQueue("p").entries] == ["l7"]  # read back at start


def test_queue_drops_old_and_keeps_the_newest(project_dir, monkeypatch):
    monkeypatch.setattr(failed, "MAX_ENTRIES", 2)
    q = failed.FailedQueue("p")
    now = time.time()
    q.upsert(SOURCE, [1], "old", [_target(T1)], now=now - failed.MAX_AGE_SEC - 1)
    for n in (2, 3, 4):
        q.upsert(SOURCE, [n], f"l{n}", [_target(T1)], now=now)
    q.flush(now=now)
    assert [e["link"] for e in failed.load("p")] == ["l3", "l4"]


def test_requests(project_dir):
    failed.request("p", failed.ALL)
    failed.request("p", failed.entry_id(SOURCE, 1))
    with pytest.raises(ValueError):
        failed.request("p", "../x")
    (project_dir / "requests" / "junk").touch()
    assert sorted(failed.take_requests("p")) == sorted([failed.ALL, failed.entry_id(SOURCE, 1)])
    assert failed.take_requests("p") == []
    assert list((project_dir / "requests").iterdir()) == []


# ── the sink: list, counters, notice ─────────────────────────────────────────

class _Notifier:
    def __init__(self):
        self.sent = []

    async def send(self, body, markup=None):
        self.sent.append((body, markup))
        return True


def _outcomes(*states):
    o = Outcomes()
    for chat, state, reason in states:
        o.expect(chat, None)
        if state == SENT:
            o.sent()
        elif state == FILTERED:
            o.filtered()
        elif state == DUPLICATE:
            o.duplicate()
        else:
            o.fail(reason)
    o.finish()
    return o


def test_sink_records_and_notices_once_a_minute(project_dir):
    projects.save_chat_names("p", {T2: "Канал Б"})
    notifier = _Notifier()
    sink = LiveSink("p", notifier, {SOURCE: {T1: [], T2: []}})
    sink.record(SOURCE, [1], "l1", _outcomes((T1, SENT, ""), (T2, FAILED, "нет прав")))
    sink.record(SOURCE, [2], "l2", _outcomes((T1, FILTERED, ""), (T2, FAILED, "нет прав")))
    run(sink.tick())
    body, markup = notifier.sent[0]
    assert body.startswith("❗ Не скопировано постов: 2. Последний: l2 → Канал Б: нет прав")
    assert markup["inline_keyboard"][0][0]["callback_data"] == "a:fail_all:p:-1:0:"

    sink.record(SOURCE, [3], "l3", _outcomes((T2, FAILED, "x")))
    run(sink.tick())
    assert len(notifier.sent) == 1  # within the minute: held until the next one

    sink.record(SOURCE, [1], "l1", _outcomes((T2, SENT, "")))  # copied again: off the list
    sink.close()
    assert [e["link"] for e in failed.load("p")] == ["l2", "l3"]
    stats = json.loads((project_dir / "stats.json").read_text())
    assert sorted(map(tuple, stats["pairs"])) == sorted([(SOURCE, T1), (SOURCE, T2)])
    (day,) = stats["days"].values()
    assert day == {f"{SOURCE}>{T1}": [1, 1, 0, 0], f"{SOURCE}>{T2}": [1, 0, 0, 3]}


# ── copying again ────────────────────────────────────────────────────────────

class _Client:
    def __init__(self, messages):
        self.messages = messages
        self.asked = []

    async def get_messages(self, chat, ids):
        self.asked.append((chat, ids))
        return [self.messages.get(i) for i in ids]


def _mirror(client, sink, db, mapping):
    return Mirroring(chat_mapping={SOURCE: mapping}, database=db, client=client,
                     logger=logging.getLogger("test.failed"), sink=sink)


def test_retry_sends_only_to_the_channels_without_it(project_dir, monkeypatch):
    sent_to = []

    async def send(client, entity, message, **kw):
        sent_to.append(entity)
        return _sent(entity)

    monkeypatch.setattr(mirroring, "send_message", send)
    db = run(InMemoryDatabase())
    run(db.insert_batch([MirrorMessage(original_id=1, original_channel=SOURCE, mirror_id=9,
                                       mirror_channel=T1, mirror_topic_id=None, source_topic_id=None)]))
    sink = LiveSink("p", None, {SOURCE: {T1: [], T2: []}})
    sink.failed.upsert(SOURCE, [1], "l1", [_target(T2)])
    sink.failed.upsert(SOURCE, [2], "gone", [_target(T2)])
    msg = make_message("again")
    client = _Client({1: msg})
    mirror = _mirror(client, sink, db, {T1: [_cfg()], T2: [_cfg()]})

    failed.request("p", failed.ALL)
    run(mirror._handle_requests(client))
    assert sent_to == [T2]
    assert sink.failed.entries == []  # copied, and the gone one forgotten


def test_retry_failing_again_stays_listed(project_dir, monkeypatch):
    async def send(client, entity, message, **kw):
        raise RuntimeError("still no")

    monkeypatch.setattr(mirroring, "send_message", send)
    sink = LiveSink("p", None, {SOURCE: {T1: []}})
    sink.failed.upsert(SOURCE, [1], "l1", [_target(T1, "first")])
    client = _Client({1: make_message("x")})
    mirror = _mirror(client, sink, run(InMemoryDatabase()), {T1: [_cfg()]})
    failed.request("p", failed.entry_id(SOURCE, 1))
    run(mirror._handle_requests(client))
    (entry,) = sink.failed.entries
    assert entry["targets"][0]["reason"] == "RuntimeError: still no"


def test_requests_are_taken_in_the_order_they_were_made(project_dir):
    """Regression: by name, 🗑 clear then ♻️ all ran as all then clear — the
    posts the admin had just told to forget were copied again first."""
    failed.request("p", failed.CLEAR)
    failed.request("p", failed.ALL)
    folder = project_dir / "requests"
    os.utime(folder / failed.CLEAR, ns=(1_000_000_000, 1_000_000_000))
    os.utime(folder / failed.ALL, ns=(2_000_000_000, 2_000_000_000))
    assert failed.take_requests("p") == [failed.CLEAR, failed.ALL]


def test_clear_request(project_dir):
    sink = LiveSink("p", None, {})
    sink.failed.upsert(SOURCE, [1], "l1", [_target(T1)])
    failed.request("p", failed.CLEAR)
    run(_mirror(_Client({}), sink, run(InMemoryDatabase()), {})._handle_requests(_Client({})))
    assert sink.failed.entries == []


def test_a_retried_post_is_counted_once_as_it_ended_up(project_dir, monkeypatch):
    """The weekly report: a post that failed, then was copied by ♻️, is one
    copied post — not a failure and a copy; one that fails again is one failure."""
    from datetime import date

    outcome = ["fail"]

    async def send(client, entity, message, **kw):
        if outcome[0] == "fail":
            raise RuntimeError("no")
        return _sent(entity)

    monkeypatch.setattr(mirroring, "send_message", send)
    sink = LiveSink("p", None, {SOURCE: {T1: []}})
    client = _Client({1: make_message("x")})
    mirror = _mirror(client, sink, run(InMemoryDatabase()), {T1: [_cfg()]})
    run(mirror._processor.new_message(SOURCE, client.messages[1], "l1"))  # live: fails
    row = lambda: sink.stats._data["days"][date.today().isoformat()][f"{SOURCE}>{T1}"]  # noqa: E731
    assert row() == [0, 0, 0, 1]

    failed.request("p", failed.ALL)
    run(mirror._handle_requests(client))  # fails again: still one failure
    assert row() == [0, 0, 0, 1] and len(sink.failed.entries) == 1

    outcome[0] = "ok"
    failed.request("p", failed.ALL)
    run(mirror._handle_requests(client))  # copied: one copied post, no failure
    assert row() == [1, 0, 0, 0] and sink.failed.entries == []


def test_a_fanout_broken_off_is_one_notice_with_a_sink(caplog):
    """__handle_exceptions: with a sink, the «❗ Не скопировано» notice carries
    the error — its log line isn't a notice of its own; without one, it is."""
    class _BadDB(InMemoryDatabase):
        async def get_messages(self, *a, **kw):
            raise RuntimeError("db down")

    with caplog.at_level(logging.ERROR, logger="test.failed"):
        run(_processor({T1: [_cfg()]}, _Sink(), run(_BadDB())).new_message(SOURCE, make_message("x"), "l"))
        run(_processor({T1: [_cfg()]}, None, run(_BadDB())).new_message(SOURCE, make_message("x"), "l"))
    with_sink, without = (r for r in caplog.records if "db down" in r.getMessage())
    assert with_sink.notice is False and without.notice is True


def test_a_floodwait_still_runs_the_clear_asked_after_it(project_dir, monkeypatch):
    """Regression: a FloodWait while copying again returned at once — the
    requests taken with it (their files already removed), a 🗑 among them,
    were lost though the panel had said «принято». The copies stop; the
    🗑 still runs."""
    async def send(client, entity, message, **kw):
        raise errors.FloodWaitError(request=None, capture=600)

    monkeypatch.setattr(mirroring, "send_message", send)
    sink = LiveSink("p", None, {SOURCE: {T1: []}})
    sink.failed.upsert(SOURCE, [1], "l1", [_target(T1)])
    client = _Client({1: make_message("x")})
    mirror = _mirror(client, sink, run(InMemoryDatabase()), {T1: [_cfg()]})
    failed.request("p", failed.ALL)
    failed.request("p", failed.CLEAR)
    folder = project_dir / "requests"
    os.utime(folder / failed.ALL, ns=(1_000_000_000, 1_000_000_000))
    os.utime(folder / failed.CLEAR, ns=(2_000_000_000, 2_000_000_000))
    run(mirror._handle_requests(client))
    assert sink.failed.entries == []


def test_a_fanout_broken_off_counts_as_a_failure_for_every_target(project_dir):
    """Regression: a post broken off before any target (ALL_CHATS: the database
    down…) was listed but not counted — the weekly report said «ошибок
    отправки: 0» and «🔇 Ничего не пришло». It's a failure of each of the
    source's directions; copied again, it's off their counters too."""
    from datetime import date

    sink = LiveSink("p", None, {SOURCE: {T1: [], T2: []}})
    broken = Outcomes()
    broken.finish(RuntimeError("db down"))
    sink.record(SOURCE, [1], "l1", broken)
    day = sink.stats._data["days"][date.today().isoformat()]
    assert day == {f"{SOURCE}>{T1}": [0, 0, 0, 1], f"{SOURCE}>{T2}": [0, 0, 0, 1]}

    (entry,) = sink.failed.entries
    sink.retrying(entry)
    assert day == {f"{SOURCE}>{T1}": [0, 0, 0, 0], f"{SOURCE}>{T2}": [0, 0, 0, 0]}


def test_stopping_tells_the_posts_not_told_yet(project_dir):
    """Regression: a post failed within the minute after the last notice (or
    cut off by the stop itself), then the mirror stopped — the files were
    written, the notice lost: the counter starts at 0 again."""
    notifier = _Notifier()
    sink = LiveSink("p", notifier, {SOURCE: {T1: []}})
    sink.record(SOURCE, [1], "l1", _outcomes((T1, FAILED, "нет прав")))
    run(sink.tick())
    sink.record(SOURCE, [2], "l2", _outcomes((T1, FAILED, "зеркало остановилось")))
    run(sink.tick())  # within the minute: held
    assert len(notifier.sent) == 1
    run(sink.aclose())
    assert notifier.sent[-1][0].startswith("❗ Не скопировано постов: 1. Последний: l2")
    assert [e["link"] for e in failed.load("p")] == ["l1", "l2"]
    run(sink.aclose())
    assert len(notifier.sent) == 2  # nothing more to tell
