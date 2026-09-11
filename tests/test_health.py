"""telemirror.health: alert on a fast-climbing restart count or a stuck unit."""

import json

from telemirror import health


def _wire(monkeypatch, tmp_path, props, prev=None):
    state = tmp_path / "state.json"
    if prev is not None:
        state.write_text(json.dumps(prev))
    monkeypatch.setattr(health, "_STATE", state)
    monkeypatch.setattr(health, "_show", lambda p: str(props.get(p, "")))
    return state


def test_no_problem_when_stable(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path,
          {"NRestarts": "4", "ActiveState": "active"},
          prev={"nrestarts": 3, "active": "active"})
    assert health.check() == []


def test_flapping_alerts(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path,
          {"NRestarts": "9", "ActiveState": "active"},
          prev={"nrestarts": 4, "active": "active"})
    problems = health.check()
    assert any("flapping" in p for p in problems)


def test_failed_state_alerts(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path,
          {"NRestarts": "2", "ActiveState": "failed"},
          prev={"nrestarts": 2, "active": "active"})
    assert any("failed" in p for p in health.check())


def test_stuck_not_active_twice_alerts(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path,
          {"NRestarts": "2", "ActiveState": "activating"},
          prev={"nrestarts": 2, "active": "activating"})
    assert any("twice in a row" in p for p in health.check())


def test_first_run_seeds_state_without_alerting(monkeypatch, tmp_path):
    state = _wire(monkeypatch, tmp_path,
                  {"NRestarts": "7", "ActiveState": "active"})
    assert health.check() == []
    assert json.loads(state.read_text())["nrestarts"] == 7


def test_deliberate_stop_for_course_backfill_does_not_alert(monkeypatch, tmp_path):
    """telemirror-past-courses.service's `Conflicts=telemirror.service` cleanly
    stops the live mirror (ActiveState=inactive) for the whole backfill, which
    can run for hours — this must not be mistaken for a stuck unit."""
    _wire(monkeypatch, tmp_path,
          {"NRestarts": "2", "ActiveState": "inactive"},
          prev={"nrestarts": 2, "active": "active"})
    assert health.check() == []

    _wire(monkeypatch, tmp_path,
          {"NRestarts": "2", "ActiveState": "inactive"},
          prev={"nrestarts": 2, "active": "inactive"})
    assert health.check() == []
