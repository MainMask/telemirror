"""Notification rules (transitions only, baseline on the first poll) and the
shared-session turns: a paused mirror comes back once the unit it yielded to
is over."""

import pytest

from bot import turns
from bot.runtime import Runtime
from bot.systemd import Systemd, parse_show
from bot.watcher import Watcher
from telemirror import projects
from tests._panel import SHOW, FakeSystemd
from tests.conftest import run


def _st(active, result="success", restarts=0, invocation="abc"):
    text = SHOW.format(active=active, sub="x", result=result)
    text = text.replace("NRestarts=0", f"NRestarts={restarts}").replace("InvocationID=abc", f"InvocationID={invocation}")
    return parse_show(text)


@pytest.fixture
def pair(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(projects, "REPO_DIR", tmp_path)
    a = projects.create_project("Альфа", "🅰️", "sessions/one.jsession")
    b = projects.create_project("Бета", "🅱️", "sessions/one.jsession")
    return a, b


def _texts(notices):
    return [n.text for n in notices]


def test_first_poll_is_baseline(pair):
    a, _ = pair
    w = Watcher()
    assert w.step({(a, a.live_unit): _st("failed"), (a, a.past_unit): _st("inactive")}) == []


def test_task_finished_ok_and_failed(pair):
    """A failed run isn't told here: OnFailure= (telemirror.alert) does — one notice."""
    a, _ = pair
    w = Watcher()
    w.step({(a, a.past_unit): _st("active"), (a, a.task_unit): _st("active")})
    out = w.step({(a, a.past_unit): _st("failed", result="exit-code"), (a, a.task_unit): _st("inactive")})
    assert _texts(out) == ["✅ 🅰️ Альфа · инструмент: закончилось успешно."]
    assert (out[0].nav.s, out[0].nav.p, out[0].nav.i) == ("unit", a.key, 2)
    assert w.step({(a, a.past_unit): _st("failed", result="exit-code"), (a, a.task_unit): _st("inactive")}) == []


def test_short_run_between_polls_is_noticed(pair):
    a, _ = pair
    w = Watcher()
    w.step({(a, a.task_unit): _st("inactive", invocation="one")})
    assert len(w.step({(a, a.task_unit): _st("inactive", invocation="two")})) == 1


def test_mirror_failed_back_and_crash_cooldown(pair):
    a, b = pair
    now = [0.0]
    w = Watcher(clock=lambda: now[0])
    w.step({(a, a.live_unit): _st("active"), (b, b.live_unit): _st("active")})
    assert _texts(w.step({(a, a.live_unit): _st("active", restarts=1)})) == [
        "⚠️ 🅰️ Альфа · зеркало: упало и запущено снова автоматически (1 раз за всё время)."
    ]
    now[0] = 60
    assert w.step({(a, a.live_unit): _st("active", restarts=2)}) == []  # within the cooldown
    # the cooldown is per mirror: another project's crash is still reported
    assert len(w.step({(b, b.live_unit): _st("active", restarts=1)})) == 1
    assert w.step({(a, a.live_unit): _st("failed", restarts=2)}) == []  # OnFailure= tells it
    assert "снова работает" in _texts(w.step({(a, a.live_unit): _st("active", restarts=2)}))[0]
    now[0] = 10_000
    assert len(w.step({(a, a.live_unit): _st("active", restarts=3)})) == 1


def test_systemctl_failure_keeps_baseline(pair):
    a, _ = pair
    w = Watcher()
    w.step({(a, a.past_unit): _st("active")})
    assert w.step({(a, a.past_unit): None}) == []
    assert len(w.step({(a, a.past_unit): _st("inactive")})) == 1


# ── turns on a shared session ───────────────────────────────────────────────


def test_a_run_on_a_shared_session_pauses_and_later_resumes(pair):
    a, b = pair
    fake = FakeSystemd({b.live_unit: "active"})
    sysd = Systemd(runner=fake)
    paused = run(turns.start(sysd, Runtime(), a, a.past_unit))
    assert [u for _, u in paused] == [b.live_unit]
    assert ["systemctl", "--no-block", "stop", b.live_unit] in fake.calls  # paused, still enabled
    assert ["systemctl", "--no-block", "start", a.past_unit] in fake.calls
    assert turns.load()[0]["resume"] == [b.live_unit]

    fake.states = {a.past_unit: "active"}
    assert run(turns.due(sysd)) == []  # A's replay runs: B stays paused
    fake.states = {}
    assert run(turns.due(sysd)) == [(a.past_unit, [b.live_unit])]  # it's over: B is back
    assert fake.calls[-1] == ["systemctl", "--no-block", "start", b.live_unit]
    assert turns.load() == []


def test_deleting_the_project_of_a_run_brings_back_the_mirrors_it_paused(pair):
    """A's replay paused B; A is deleted (its units turned off). Its unit is no
    project's now — systemctl isn't asked about it — and B must still come back."""
    a, b = pair
    fake = FakeSystemd({b.live_unit: "active"})
    sysd = Systemd(runner=fake)
    run(turns.start(sysd, Runtime(), a, a.past_unit))
    fake.states = {a.past_unit: "active"}
    run(turns.due(sysd))  # the replay is seen running
    projects.delete_project(a.key)
    fake.states = {}
    assert run(turns.due(sysd)) == [(a.past_unit, [b.live_unit])]
    assert fake.calls[-1] == ["systemctl", "--no-block", "start", b.live_unit]
    assert turns.load() == []


def test_a_queued_start_is_not_mistaken_for_an_ended_one(pair):
    a, b = pair
    fake = FakeSystemd({b.live_unit: "active"})
    sysd = Systemd(runner=fake)
    run(turns.start(sysd, Runtime(), a, a.past_unit))
    fake.states = {}  # A's start is still queued: not yet seen running
    assert run(turns.due(sysd)) == []
    assert turns.load()


def test_a_replay_brings_its_own_mirror_back(pair):
    a, _ = pair
    fake = FakeSystemd({a.live_unit: "active"})
    sysd = Systemd(runner=fake)
    run(turns.start(sysd, Runtime(), a, a.past_unit))
    assert turns.load()[0]["resume"] == [a.live_unit]


def test_a_mirror_replaces_another_mirror_on_its_session(pair):
    a, b = pair
    fake = FakeSystemd({b.live_unit: "active"})
    run(turns.start(Systemd(runner=fake), Runtime(), a, a.live_unit))
    assert ["systemctl", "--no-block", "disable", "--now", b.live_unit] in fake.calls
    assert ["systemctl", "--no-block", "enable", "--now", a.live_unit] in fake.calls
    assert turns.load() == []


def test_a_run_started_over_another_takes_over_its_paused_mirrors(pair):
    """A's replay paused B; a task started meanwhile stops the replay. B must
    wait for the task — brought back when the replay stopped, B's start would
    kill the task (Conflicts=) or collide with it on the session."""
    a, b = pair
    fake = FakeSystemd({b.live_unit: "active"})
    sysd = Systemd(runner=fake)
    run(turns.start(sysd, Runtime(), a, a.past_unit))
    fake.states = {a.past_unit: "active"}
    run(turns.due(sysd))  # the replay is seen running
    run(turns.start(sysd, Runtime(), a, a.task_unit))  # stops the replay
    assert [(e["after"], e["resume"]) for e in turns.load()] == [(a.task_unit, [b.live_unit])]
    fake.states = {a.task_unit: "active"}
    assert run(turns.due(sysd)) == []  # the replay is over, the task runs: B stays paused
    fake.states = {}
    assert run(turns.due(sysd)) == [(a.task_unit, [b.live_unit])]


def test_a_mirror_started_over_a_run_turns_off_the_mirrors_paused_for_it(pair):
    """A's replay paused B; then A's mirror is started (it stops the replay).
    One mirror per session: B is turned off, not brought back next to A."""
    a, b = pair
    fake = FakeSystemd({b.live_unit: "active"})
    sysd = Systemd(runner=fake)
    run(turns.start(sysd, Runtime(), a, a.past_unit))
    fake.states = {a.past_unit: "active"}
    run(turns.start(sysd, Runtime(), a, a.live_unit))
    assert ["systemctl", "--no-block", "disable", "--now", b.live_unit] in fake.calls
    assert turns.load() == []


def test_nothing_to_pause_records_nothing(pair):
    a, _ = pair
    run(turns.start(Systemd(runner=FakeSystemd()), Runtime(), a, a.live_unit))
    assert turns.load() == []


def test_the_watch_loop_notifies_and_brings_paused_mirrors_back(pair, monkeypatch):
    """One round of the background loop: a replay that ended is reported with a
    button to its card, and the mirror paused for it is started again."""
    import asyncio

    from aiogram.methods import SendMessage

    from bot import watcher
    from tests._panel import ADMIN_ID, make_bot

    a, b = pair
    fake = FakeSystemd({b.live_unit: "active", a.past_unit: "active"})
    sysd = Systemd(runner=fake)
    run(turns.start(sysd, Runtime(), a, a.past_unit))  # pauses B
    bot, session = make_bot()
    rounds = []

    async def tick(_seconds):
        rounds.append(1)
        if len(rounds) == 1:
            fake.states = {}  # between the rounds the replay ends (and B is down)
            return
        raise asyncio.CancelledError

    monkeypatch.setattr(watcher.asyncio, "sleep", tick)
    with pytest.raises(asyncio.CancelledError):
        run(watcher.watch(bot, sysd, frozenset({ADMIN_ID})))
    texts = [m.text for m in session.of(SendMessage)]
    assert any("🅰️ Альфа · копирование истории: закончилось успешно" in t for t in texts)
    assert any(t.startswith("▶️ Снова запущено: 🅱️ Бета · зеркало") for t in texts)
    assert ["systemctl", "--no-block", "start", b.live_unit] in fake.calls


def test_a_deleted_projects_units_are_forgotten(pair):
    a, b = pair
    w = Watcher()
    w.step({(a, a.live_unit): _st("active"), (b, b.live_unit): _st("active")})
    w.forget_gone({a.live_unit})
    assert set(w._prev) == {a.live_unit}


def test_a_run_stopped_from_outside_is_not_reported_as_finished(pair):
    """systemd counts a SIGTERM stop (⏹, Conflicts=) as Result=success: the
    notice tells it by ExecMainCode/ExecMainStatus (killed, or the replay's 143)."""
    a, _ = pair
    w = Watcher()
    w.step({(a, a.task_unit): _st("active"), (a, a.past_unit): _st("active")})
    killed = parse_show(SHOW.format(active="inactive", sub="dead", result="success")
                        .replace("ExecMainCode=1", "ExecMainCode=2").replace("ExecMainStatus=0", "ExecMainStatus=15"))
    replay_stopped = parse_show(SHOW.format(active="inactive", sub="dead", result="success")
                                .replace("ExecMainStatus=0", "ExecMainStatus=143"))
    assert _texts(w.step({(a, a.task_unit): killed, (a, a.past_unit): replay_stopped})) == [
        "⏹ 🅰️ Альфа · инструмент: прервано, не закончив работу.",
        "⏹ 🅰️ Альфа · копирование истории: прервано, не закончив работу.",
    ]
