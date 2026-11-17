"""telemirror.health: alert on a fast-climbing restart count or a stuck unit
(per project live mirror), and main() must surface a failed alert send, not
exit 0 regardless (the same SPOF class already fixed in telemirror.alert's own
entrypoint)."""

import json

import pytest

from telemirror import health


UNIT = "telemirror@live.service"


def _wire(monkeypatch, tmp_path, props, prev=None):
    state = tmp_path / "state.json"
    if prev is not None:
        state.write_text(json.dumps({UNIT: prev}))
    monkeypatch.setattr(health, "_STATE", state)
    monkeypatch.setattr(health, "_units", lambda: [UNIT])
    monkeypatch.setattr(health, "_show", lambda unit, p: str(props.get(p, "")))
    return state


def _problems():
    return [p for _, problems in health.check() for p in problems]


def test_no_problem_when_stable(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path,
          {"NRestarts": "4", "ActiveState": "active"},
          prev={"nrestarts": 3, "active": "active"})
    assert _problems() == []


def test_flapping_alerts(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path,
          {"NRestarts": "9", "ActiveState": "active"},
          prev={"nrestarts": 4, "active": "active"})
    problems = _problems()
    assert any("flapping" in p for p in problems)


def test_failed_state_alerts(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path,
          {"NRestarts": "2", "ActiveState": "failed"},
          prev={"nrestarts": 2, "active": "active"})
    assert any("failed" in p for p in _problems())


def test_stuck_not_active_twice_alerts(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path,
          {"NRestarts": "2", "ActiveState": "activating"},
          prev={"nrestarts": 2, "active": "activating"})
    assert any("twice in a row" in p for p in _problems())


def test_first_run_seeds_state_without_alerting(monkeypatch, tmp_path):
    state = _wire(monkeypatch, tmp_path,
                  {"NRestarts": "7", "ActiveState": "active"})
    assert _problems() == []
    assert json.loads(state.read_text())[UNIT]["nrestarts"] == 7


def test_deliberate_stop_for_history_replay_does_not_alert(monkeypatch, tmp_path):
    """telemirror-past@<key>.service's `Conflicts=telemirror@<key>.service`
    cleanly stops the live mirror (ActiveState=inactive) for the whole replay,
    which can run for hours — this must not be mistaken for a stuck unit."""
    _wire(monkeypatch, tmp_path,
          {"NRestarts": "2", "ActiveState": "inactive"},
          prev={"nrestarts": 2, "active": "active"})
    assert _problems() == []

    _wire(monkeypatch, tmp_path,
          {"NRestarts": "2", "ActiveState": "inactive"},
          prev={"nrestarts": 2, "active": "inactive"})
    assert _problems() == []


def test_main_exits_nonzero_when_alert_not_delivered(monkeypatch):
    monkeypatch.setattr(health, "check", lambda: [(UNIT, ["⚠️ x: ActiveState=failed"])])
    monkeypatch.setattr(health.alert, "journal_tail", lambda unit, lines=15: "boom")
    monkeypatch.setattr(health.alert, "send_alert", lambda text: False)
    with pytest.raises(SystemExit) as exc_info:
        health.main()
    assert exc_info.value.code != 0


def test_main_exits_zero_when_alert_delivered(monkeypatch):
    monkeypatch.setattr(health, "check", lambda: [(UNIT, ["⚠️ x: ActiveState=failed"])])
    monkeypatch.setattr(health.alert, "journal_tail", lambda unit, lines=15: "boom")
    monkeypatch.setattr(health.alert, "send_alert", lambda text: True)
    with pytest.raises(SystemExit) as exc_info:
        health.main()
    assert exc_info.value.code == 0


def test_main_exits_zero_and_skips_alert_when_no_problems(monkeypatch):
    monkeypatch.setattr(health, "check", list)

    def _no_alert(text):
        raise AssertionError("must not send an alert when nothing's wrong")

    monkeypatch.setattr(health.alert, "send_alert", _no_alert)
    with pytest.raises(SystemExit) as exc_info:
        health.main()
    assert exc_info.value.code == 0


def test_failed_state_alerts_only_once(monkeypatch, tmp_path):
    """OnFailure= already alerts on entering `failed`; health must not repeat
    the same ActiveState=failed alert on every 10-minute tick after that."""
    _wire(monkeypatch, tmp_path,
          {"NRestarts": "2", "ActiveState": "failed"},
          prev={"nrestarts": 2, "active": "failed"})
    assert _problems() == []


def test_each_project_unit_is_checked_on_its_own(monkeypatch, tmp_path):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({
        "telemirror@a.service": {"nrestarts": 1, "active": "active"},
        "telemirror@b.service": {"nrestarts": 1, "active": "active"},
    }))
    props = {
        "telemirror@a.service": {"NRestarts": "1", "ActiveState": "active"},
        "telemirror@b.service": {"NRestarts": "9", "ActiveState": "active"},
    }
    monkeypatch.setattr(health, "_STATE", state)
    monkeypatch.setattr(health, "_units", lambda: list(props))
    monkeypatch.setattr(health, "_show", lambda unit, p: props[unit][p])
    found = health.check()
    assert [unit for unit, _ in found] == ["telemirror@b.service"]
    assert json.loads(state.read_text())["telemirror@b.service"]["nrestarts"] == 9
