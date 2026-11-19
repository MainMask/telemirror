"""The live mirror stopping (``Mirroring.__connect_client``'s ``finally``): what
was under way at that moment isn't lost — a post cut off by the stop is in the
not-copied list, a ban's notice reaches the admins."""

import asyncio
import logging

import pytest
from telethon import errors
from telethon.tl import types

import telemirror.mirroring as mirroring
from telemirror import failed, projects
from telemirror.directions import DirectionConfig
from telemirror.messagefilters import EmptyMessageFilter
from telemirror.mirroring import Mirroring
from telemirror.outcomes import Outcomes
from telemirror.sink import LiveSink
from telemirror.storage import InMemoryDatabase
from tests.conftest import make_message, run

SOURCE, TARGET = -1001000000000, -1002000000001


class _Client:
    """``__connect_client``'s side of a TelegramClient. ``run_until_disconnected``
    plays the session (``live``); ``disconnect`` cancels the handler tasks still
    under way and waits for them, as Telethon's does."""

    def __init__(self, live):
        self._live = live
        self._connected = False
        self.tasks = set()

    def is_connected(self):
        return self._connected

    async def connect(self):
        self._connected = True

    def add_event_handler(self, *args):
        pass

    async def get_me(self):
        return types.User(id=1, first_name="Me")

    async def run_until_disconnected(self):
        await self._live(self)

    async def disconnect(self):
        for task in self.tasks:
            task.cancel()
        if self.tasks:
            await asyncio.wait(self.tasks)
        self._connected = False


class _Notifier:
    def __init__(self):
        self.sent = []

    async def send(self, body, markup=None):
        self.sent.append(body)
        return True


@pytest.fixture
def project_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path)
    (tmp_path / "p").mkdir()
    return tmp_path / "p"


def _cfg():
    return DirectionConfig(disable_delete=False, disable_edit=False, filters=EmptyMessageFilter())


def test_a_post_cut_off_by_the_stop_is_saved_in_the_list(project_dir, monkeypatch):
    """Regression: the list was written before ``client.disconnect()`` — the one
    that cancels the posts under way — so a post cut off by ⏹ / a restart was
    recorded («зеркало остановилось») only in memory, and lost."""
    sending = asyncio.Event()

    async def send(client, entity, message, **kw):
        sending.set()
        await asyncio.Event().wait()  # still sending when the stop comes

    monkeypatch.setattr(mirroring, "send_message", send)
    sink = LiveSink("p", None, {SOURCE: {TARGET: []}})
    mirror = Mirroring(chat_mapping={SOURCE: {TARGET: [_cfg()]}}, database=run(InMemoryDatabase()),
                       client=object(), logger=logging.getLogger("test.shutdown"), sink=sink)

    async def live(client):
        client.tasks.add(asyncio.create_task(
            mirror._processor.new_message(SOURCE, make_message("x"), "l1")))
        await sending.wait()
        raise asyncio.CancelledError  # SIGTERM: cancel_on_sigterm cancels the main task here

    with pytest.raises(asyncio.CancelledError):
        run(mirror._Mirroring__connect_client(_Client(live)))
    (entry,) = failed.load("p")
    assert entry["link"] == "l1" and entry["targets"][0]["reason"] == "зеркало остановилось"


def test_a_ban_is_told_to_the_admins(monkeypatch):
    """Regression: the ban's critical log line waits out the handler's 5 s
    debounce, and the ``finally`` right after it closed the handler — the
    pending notice was dropped, the admins never told."""
    notifier = _Notifier()
    mirror = Mirroring(chat_mapping={}, database=run(InMemoryDatabase()), client=object(),
                       logger=logging.getLogger("telemirror.test.shutdown"), notifier=notifier)

    async def live(client):
        raise errors.UserDeactivatedBanError(request=None)

    run(mirror._Mirroring__connect_client(_Client(live)))
    assert any("Account banned" in body for body in notifier.sent)


def _photo_message(mid, pid):
    m = make_message("", media=types.MessageMediaPhoto(photo=types.Photo(
        id=pid, access_hash=0, file_reference=b"", date=None, sizes=[], dc_id=1)))
    m.id = mid
    return m


def test_an_album_cut_off_by_the_stop_is_saved_in_the_list(project_dir, monkeypatch):
    """Regression: Telethon dispatches an album from a task of its own
    (``AlbumHack``), not among the ones ``disconnect()`` cancels — the album
    still under way was recorded after the list was written, and lost."""
    sending = asyncio.Event()

    async def send_file(client, entity, caption, file, **kw):
        sending.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(mirroring, "send_file", send_file)
    sink = LiveSink("p", None, {SOURCE: {TARGET: []}})
    mirror = Mirroring(chat_mapping={SOURCE: {TARGET: [_cfg()]}}, database=run(InMemoryDatabase()),
                       client=object(), logger=logging.getLogger("test.shutdown"), sink=sink)
    album_tasks = []

    async def live(client):
        album_tasks.append(asyncio.create_task(mirror._processor.new_album(  # not in client.tasks
            SOURCE, [_photo_message(1, 5), _photo_message(2, 6)], "album")))
        await sending.wait()
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        run(mirror._Mirroring__connect_client(_Client(live)))
    (entry,) = failed.load("p")
    assert entry["link"] == "album" and entry["targets"][0]["reason"] == "зеркало остановилось"


def test_a_hung_bot_api_does_not_hold_the_stop(project_dir, monkeypatch):
    """Regression: the last notices were sent one after another with no limit
    (20 s per admin each) — a Bot API that doesn't answer outlasted systemd's
    90 s to stop. Now they have one deadline; the files are written before."""
    class _Hung:
        async def send(self, body, markup=None):
            await asyncio.Event().wait()

    monkeypatch.setattr(Mirroring, "STOP_NOTICES_SEC", 0.05)
    sink = LiveSink("p", _Hung(), {SOURCE: {TARGET: []}})
    mirror = Mirroring(chat_mapping={SOURCE: {TARGET: [_cfg()]}}, database=run(InMemoryDatabase()),
                       client=object(), logger=logging.getLogger("telemirror.test.shutdown"),
                       notifier=_Hung(), sink=sink)
    outcomes = Outcomes()
    outcomes.expect(TARGET, None)
    outcomes.finish(RuntimeError("no"))
    sink.record(SOURCE, [1], "l1", outcomes)  # a not-copied notice due at the stop

    async def live(client):
        raise errors.UserDeactivatedBanError(request=None)

    run(mirror._Mirroring__connect_client(_Client(live)))
    assert [e["link"] for e in failed.load("p")] == ["l1"]
    assert not any(isinstance(h, mirroring.NoticeLogHandler)
                   for h in logging.getLogger("telemirror").handlers)


def test_fan_outs_waiting_their_dedup_turn_are_all_cut_off(project_dir, monkeypatch):
    """Regression: the fan-outs were cancelled one by one — the first one's
    dedup turn passed to the next, which started sending through the closed
    client (and failed with its error, not «зеркало остановилось»)."""
    dedup = DirectionConfig(disable_delete=False, disable_edit=False, filters=EmptyMessageFilter(),
                            dedup_hours=24)
    other = SOURCE - 1
    calls = []

    async def send(client, entity, message, **kw):
        calls.append(entity)
        await asyncio.Event().wait()

    monkeypatch.setattr(mirroring, "send_message", send)
    sink = LiveSink("p", None, {SOURCE: {TARGET: []}, other: {TARGET: []}})
    mirror = Mirroring(chat_mapping={SOURCE: {TARGET: [dedup]}, other: {TARGET: [dedup]}},
                       database=run(InMemoryDatabase()), client=object(),
                       logger=logging.getLogger("test.shutdown"), sink=sink)
    text = "Новость дня: что-то очень важное случилось"
    tasks = []

    async def live(client):
        for chat, link in ((SOURCE, "first"), (other, "second")):  # not in client.tasks
            tasks.append(asyncio.create_task(mirror._processor.new_message(chat, make_message(text), link)))
        while not calls:
            await asyncio.sleep(0)
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        run(mirror._Mirroring__connect_client(_Client(live)))
    assert len(calls) == 1
    assert {e["link"]: e["targets"][0]["reason"] for e in failed.load("p")} == {
        "first": "зеркало остановилось", "second": "зеркало остановилось"}


def test_an_album_still_within_telethons_delay_is_cut_off_too(project_dir, monkeypatch):
    """Regression: an album is dispatched a second after its last item — one
    that came just before the stop started after the files were written, and
    was lost."""
    calls = []

    async def send_file(client, entity, caption, file, **kw):
        calls.append(entity)
        await asyncio.Event().wait()

    monkeypatch.setattr(mirroring, "send_file", send_file)
    monkeypatch.setattr(mirroring, "_ALBUM_EVENT_GRACE_SEC", 0.2)
    sink = LiveSink("p", None, {SOURCE: {TARGET: []}})
    mirror = Mirroring(chat_mapping={SOURCE: {TARGET: [_cfg()]}}, database=run(InMemoryDatabase()),
                       client=object(), logger=logging.getLogger("test.shutdown"), sink=sink)
    hacks = []

    async def album_hack():  # Telethon's AlbumHack: waits out the delay, then dispatches
        await asyncio.sleep(0.1)
        await mirror._processor.new_album(SOURCE, [_photo_message(1, 5), _photo_message(2, 6)], "album")

    async def live(client):
        mirror._last_update_ts = mirroring.time.monotonic()  # the album's last item
        hacks.append(asyncio.create_task(album_hack()))
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        run(mirror._Mirroring__connect_client(_Client(live)))
    (entry,) = failed.load("p")
    assert entry["link"] == "album" and entry["targets"][0]["reason"] == "зеркало остановилось"
    assert calls == []  # not tried on the closed client (its ConnectionError the reason)


def test_a_turn_handed_over_while_disconnecting_does_not_start(project_dir, monkeypatch):
    """Regression: ``disconnect()`` cancelled the fan-out holding a dedup turn,
    and an album waiting for it (a task Telethon doesn't track) got it and
    started sending through the closing client."""
    dedup = DirectionConfig(disable_delete=False, disable_edit=False, filters=EmptyMessageFilter(),
                            dedup_hours=24)
    other = SOURCE - 1
    calls = []

    async def send(client, entity, message, **kw):
        calls.append(entity)
        await asyncio.Event().wait()

    monkeypatch.setattr(mirroring, "send_message", send)
    sink = LiveSink("p", None, {SOURCE: {TARGET: []}, other: {TARGET: []}})
    mirror = Mirroring(chat_mapping={SOURCE: {TARGET: [dedup]}, other: {TARGET: [dedup]}},
                       database=run(InMemoryDatabase()), client=object(),
                       logger=logging.getLogger("test.shutdown"), sink=sink)
    text = "Новость дня: что-то очень важное случилось"
    untracked = []

    async def live(client):
        client.tasks.add(asyncio.create_task(mirror._processor.new_message(SOURCE, make_message(text), "first")))
        while not calls:
            await asyncio.sleep(0)
        untracked.append(asyncio.create_task(mirror._processor.new_message(other, make_message(text), "second")))
        await asyncio.sleep(0)  # waiting for the turn
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        run(mirror._Mirroring__connect_client(_Client(live)))
    assert len(calls) == 1
    assert {e["link"]: e["targets"][0]["reason"] for e in failed.load("p")} == {
        "first": "зеркало остановилось", "second": "зеркало остановилось"}


def test_a_service_message_during_the_stop_is_not_listed_as_cut_off(project_dir):
    """Regression: the stop was checked before the service-message skip — a pin
    or a join landing during ⏹ became «❗ Не скопировано» for every channel."""
    sink = LiveSink("p", None, {SOURCE: {TARGET: []}})
    mirror = Mirroring(chat_mapping={SOURCE: {TARGET: [_cfg()]}}, database=run(InMemoryDatabase()),
                       client=object(), logger=logging.getLogger("test.shutdown"), sink=sink)
    pin = types.MessageService(id=1, peer_id=types.PeerChannel(1000), date=None,
                               action=types.MessageActionPinMessage())
    mirror._processor.stop()
    run(mirror._processor.new_message(SOURCE, pin, "pin"))
    assert sink.failed.entries == []
