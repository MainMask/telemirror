"""The weekly report (python -m telemirror.report) from the live mirror's counters."""

from datetime import date

import pytest

from telemirror import failed, projects, report, stats
from telemirror.outcomes import Target

S, A, B, C = -1001, -1002, -1003, -1004
MONDAY = date(2026, 11, 23)


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path)
    (tmp_path / "p").mkdir()
    return "p"


def _counts(st, target, sent=0, filtered=0, dup=0, fail=0, day=date(2026, 11, 18)):
    for state, n in (("sent", sent), ("filtered", filtered), ("dup", dup), ("failed", fail)):
        for _ in range(n):
            st.add(S, target, state, day)


def test_report_sections(project):
    projects.save_chat_names(project, {S: "Источник", A: "Канал А"})
    st = stats.Stats(project, [(S, A), (S, B), (S, C)])
    _counts(st, A, sent=1200, dup=3, fail=4)
    _counts(st, C, sent=1, filtered=19)
    _counts(st, A, sent=99, day=date(2026, 11, 10))  # the week before: not counted
    st.flush(today=MONDAY)
    q = failed.FailedQueue(project)
    q.upsert(S, [1], "l", [Target(A, None, "failed", "x")])
    q.flush()

    text = report.report_text(project, MONDAY)
    assert text.startswith("📈 Сводка за неделю 16.11–22.11")
    assert "Скопировано: 1 201 · отсеяно фильтрами: 19 · повторов: 3 · ошибок отправки: 4" in text
    assert "🔇 Ничего не пришло за неделю (1):\n• Источник → -1003" in text
    assert "⚠️ Больше всего ошибок отправки:\n• Источник → Канал А — 4" in text
    assert "🧹 Фильтры отсеивают почти всё:\n• Источник → -1004 — 95% из 20" in text
    assert "❗ Ждут повтора: 1" in text


def test_report_long_lists_and_an_idle_week(project, monkeypatch):
    st = stats.Stats(project, [(S, -2000 - n) for n in range(15)])
    st.add(S, -2000, "sent", date(2026, 11, 20))
    st.flush(today=MONDAY)
    text = report.report_text(project, MONDAY)
    assert "(14):" in text and "…и ещё 4" in text

    assert "всю неделю не работало" in report.report_text(project, date(2027, 1, 4))


def test_send_reports(project, monkeypatch):
    sent = []

    class _Notifier:
        def send_sync(self, body, markup=None):
            sent.append((body, markup))
            return True

    monkeypatch.setattr(report.BotNotifier, "from_env", classmethod(lambda cls, *a: _Notifier()))
    p = projects.Project("p", "P", "📁", "s", "c", 8000)
    assert report.send_reports([p], MONDAY) is None  # never counted: nothing to say
    stats.Stats(project, [(S, A)]).flush(today=MONDAY)
    assert report.send_reports([p], MONDAY) is True
    assert sent[0][1] is None  # nothing to copy again: no buttons

    monkeypatch.setattr(report.BotNotifier, "from_env", classmethod(lambda cls, *a: None))
    assert report.send_reports([p], MONDAY) is False


def test_quiet_days(project):
    st = stats.Stats(project, [(S, A), (S, B)])
    _counts(st, A, filtered=1, day=date(2026, 11, 18))
    _counts(st, A, sent=1, day=date(2026, 11, 10))
    st.flush(today=MONDAY)
    data = stats.load(project)
    assert stats.quiet_days(data, [(S, A)], MONDAY) == 5  # the latest day counts, filtered too
    assert stats.quiet_days(data, [(S, A), (S, B)], MONDAY) == 5  # a direction: its freshest pair
    assert stats.quiet_days(data, [(S, B)], MONDAY) == stats.KEEP_DAYS + 1  # nothing in the days kept
    assert stats.quiet_days(data, [(S, C)], MONDAY) is None  # the mirror hasn't run with it


def test_a_quiet_week_is_not_a_stopped_mirror(project):
    """The mirror ran all week, its sources posted nothing: the days it ran are
    kept ({}), so the report says the directions got nothing — not that the
    mirror didn't run."""
    st = stats.Stats(project, [(S, A)])
    for n in range(1, 8):  # flushed every day of the week, no post
        st.flush(today=date(2026, 11, 16 + n - 1))
    text = report.report_text(project, MONDAY)
    assert "не работало" not in text
    assert "🔇 Ничего не пришло за неделю (1):" in text
    assert "Скопировано: 0" in text
