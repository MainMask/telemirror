"""NoticeLogHandler: the mirror's WARNING+ log records go to the panel's admins
through the bot — merged, rate-limited, never leaking timers or tasks."""

import asyncio
import logging

from telemirror.mirroring import NoticeLogHandler


class FakeNotifier:
    def __init__(self):
        self.sent = []

    async def send(self, body):
        self.sent.append(body)
        return True


def test_prune_cooldowns_drops_expired():
    loop = asyncio.new_event_loop()
    try:
        h = NoticeLogHandler(FakeNotifier(), loop)
        now = loop.time()
        h._cooldown_until = {
            "old-1": now - 10,
            "old-2": now - 1,
            "fresh": now + 30,
        }
        h._enqueue("brand new message")

        assert "old-1" not in h._cooldown_until
        assert "old-2" not in h._cooldown_until
        assert "fresh" in h._cooldown_until
    finally:
        loop.close()


def test_send_task_is_referenced():
    loop = asyncio.new_event_loop()
    try:
        notifier = FakeNotifier()
        h = NoticeLogHandler(notifier, loop)
        h._counts["msg"] = 3

        async def drive():
            h._send("msg")
            assert h._tasks, "send task must be strongly referenced"
            await asyncio.sleep(0)

        loop.run_until_complete(drive())
        assert h._tasks == set()  # done-callback cleaned it up
        assert notifier.sent == ["msg (×3)"]
    finally:
        loop.close()


def test_records_get_a_russian_level():
    h = NoticeLogHandler(FakeNotifier(), asyncio.new_event_loop())
    record = logging.LogRecord("telemirror", logging.ERROR, "", 0, "send failed", None, None)
    assert h._format_record(record) == "‼️ Ошибка: send failed"
    h._loop.close()


def test_at_most_ten_a_minute_then_says_how_many_were_held_back():
    loop = asyncio.new_event_loop()
    try:
        notifier = FakeNotifier()
        h = NoticeLogHandler(notifier, loop)

        async def drive():
            for n in range(h._PER_MINUTE + 3):
                h._send(f"distinct {n}")
            await asyncio.sleep(0)
            assert len(notifier.sent) == h._PER_MINUTE
            await asyncio.sleep(0)  # the done-callbacks release the in-flight slots
            h._sent_at.clear()  # a minute later
            h._send("after the burst")
            await asyncio.sleep(0)

        loop.run_until_complete(drive())
        assert notifier.sent[-1].startswith("after the burst")
        assert "ещё 3 сообщ." in notifier.sent[-1]
    finally:
        loop.close()


def test_in_flight_sends_are_capped():
    """A send may hang on the network: a burst of distinct warnings must not
    pile up unbounded tasks."""
    loop = asyncio.new_event_loop()
    try:
        hold = asyncio.Event()

        class SlowNotifier(FakeNotifier):
            async def send(self, body):
                await hold.wait()

        h = NoticeLogHandler(SlowNotifier(), loop)
        h._PER_MINUTE = 1000

        async def drive():
            for n in range(3 * h._MAX_IN_FLIGHT):
                h._send(f"distinct {n}")
            assert len(h._tasks) == h._MAX_IN_FLIGHT
            hold.set()
            await asyncio.sleep(0)

        loop.run_until_complete(drive())
    finally:
        loop.close()


def test_a_notices_own_trouble_is_not_sent():
    loop = asyncio.new_event_loop()
    try:
        h = NoticeLogHandler(FakeNotifier(), loop)
        h.emit(logging.LogRecord("telemirror.notify", logging.WARNING, "", 0, "bot down", None, None))
        loop.run_until_complete(asyncio.sleep(0))
        assert h._counts == {} and h._timers == {}
    finally:
        loop.close()


def test_close_cancels_pending_debounced_sends():
    loop = asyncio.new_event_loop()
    try:
        h = NoticeLogHandler(FakeNotifier(), loop)
        h._enqueue("pending")
        timer = h._timers["pending"]
        h.close()
        assert timer.cancelled() and h._timers == {} and h._counts == {}
    finally:
        loop.close()


def test_a_burst_with_no_notice_after_it_still_says_how_many_were_held_back():
    """The burst ends and nothing else comes: the count held back (the rate, or
    the sends still under way) is told by itself a minute later — once."""
    loop = asyncio.new_event_loop()
    try:
        notifier = FakeNotifier()
        h = NoticeLogHandler(notifier, loop)
        h._HELD_BACK_SEC = 0.01

        async def drive():
            for n in range(h._PER_MINUTE + 3):
                h._send(f"distinct {n}")
            await asyncio.sleep(0)
            assert len(notifier.sent) == h._PER_MINUTE
            h._sent_at.clear()  # a minute later
            await asyncio.sleep(0.05)

        loop.run_until_complete(drive())
        assert notifier.sent[h._PER_MINUTE:] == [
            "⚠️ Ещё 3 сообщ. не отправлено, чтобы не засыпать чат, — они в журнале."
        ]
        assert h._held_back == 0 and h._held_timer is None
    finally:
        loop.close()


def test_aclose_sends_what_waits_even_past_the_rate():
    """Regression: a ban comes after a burst of errors — the rate (or the sends
    under way) held its notice back, and ``close`` dropped the held-back one:
    the admins never told. Stopping, what waits goes out anyway."""
    loop = asyncio.new_event_loop()
    try:
        notifier = FakeNotifier()
        h = NoticeLogHandler(notifier, loop)

        async def drive():
            for n in range(h._PER_MINUTE + 2):
                h._send(f"distinct {n}")  # the burst: two held back
            h._enqueue("🚨 Критично: Account banned")
            await h.aclose()

        loop.run_until_complete(drive())
        assert notifier.sent[-1] == (
            "🚨 Критично: Account banned\n\n…и ещё 2 сообщ. не отправлено, "
            "чтобы не засыпать чат, — они в журнале."
        )
    finally:
        loop.close()


def test_aclose_tells_the_held_back_count_with_nothing_else_waiting():
    loop = asyncio.new_event_loop()
    try:
        notifier = FakeNotifier()
        h = NoticeLogHandler(notifier, loop)

        async def drive():
            for n in range(h._PER_MINUTE + 1):
                h._send(f"distinct {n}")
            await h.aclose()

        loop.run_until_complete(drive())
        assert notifier.sent[-1] == "⚠️ Ещё 1 сообщ. не отправлено, чтобы не засыпать чат, — они в журнале."
    finally:
        loop.close()


def test_aclose_waits_for_every_admin_however_slow(monkeypatch):
    """Regression: aclose waited SEND_TIMEOUT for all of it — a notice goes to
    the admins one by one (each request with its own timeout), so a slow first
    one cut the next ones off. (A short timeout, if there is one at all.)"""
    import telemirror.mirroring as mirroring

    monkeypatch.setattr(mirroring, "SEND_TIMEOUT", 0.01, raising=False)
    loop = asyncio.new_event_loop()
    try:
        done = []

        class SlowNotifier:
            async def send(self, body):
                await asyncio.sleep(0.05)
                done.append(body)
                return True

        h = NoticeLogHandler(SlowNotifier(), loop)

        async def drive():
            h._enqueue("ban")
            await h.aclose()

        loop.run_until_complete(drive())
        assert done == ["ban"]
    finally:
        loop.close()


def test_aclose_cancels_the_held_back_timer():
    """Regression: aclose told the held-back count and dropped the timer that
    would have told it — without cancelling it: it outlived the handler."""
    loop = asyncio.new_event_loop()
    try:
        h = NoticeLogHandler(FakeNotifier(), loop)

        async def drive():
            for n in range(h._PER_MINUTE + 1):
                h._send(f"distinct {n}")
            timer = h._held_timer
            await h.aclose()
            return timer

        timer = loop.run_until_complete(drive())
        assert timer is not None and timer.cancelled()
    finally:
        loop.close()


def test_aclose_tells_what_waits_in_one_notice_the_latest_first():
    """Regression: what waited went out past every limit, one send each — a
    burst before a ban was refused by Telegram past its per-chat limit, the
    ban's notice (logged last) the likeliest. One notice now, the ban first."""
    loop = asyncio.new_event_loop()
    try:
        notifier = FakeNotifier()
        h = NoticeLogHandler(notifier, loop)

        async def drive():
            for n in range(30):
                h._enqueue(f"distinct {n}")
            h._enqueue("🚨 Критично: Account banned")
            await h.aclose()

        loop.run_until_complete(drive())
        (body,) = notifier.sent
        assert body.startswith("🚨 Критично: Account banned\n\ndistinct 29\n\n")
        assert body.endswith("distinct 0")
    finally:
        loop.close()


def test_aclose_does_not_tell_a_text_again_when_its_timer_fires_during_the_wait(monkeypatch):
    """Regression: aclose told what waited but left its debounce timers running
    while it waited for the sends — a slow Bot API, and the timer sent the same
    notice a second time."""
    monkeypatch.setattr(NoticeLogHandler, "_DEBOUNCE", 0.05)
    loop = asyncio.new_event_loop()
    try:
        sent = []

        class SlowNotifier:
            async def send(self, body):
                sent.append(body)
                await asyncio.sleep(0.2)  # longer than the debounce left
                return True

        h = NoticeLogHandler(SlowNotifier(), loop)

        async def drive():
            h._enqueue("🚨 Критично: Account banned")
            await h.aclose()

        loop.run_until_complete(drive())
        assert sent == ["🚨 Критично: Account banned"]
    finally:
        loop.close()
