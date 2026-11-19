"""The weekly report to the panel's admins — one message per project: what
its live mirror copied over the last 7 days, which directions got nothing,
where sends fail, where the filters drop almost everything, and how many posts
wait to be copied again. Run by ``telemirror-report.timer`` (Mondays, 10:00).

    python -m telemirror.report
"""

import logging
import sys
from datetime import date, timedelta
from typing import Dict, List, Optional

from telemirror import failed, stats
from telemirror.misc.log_setup import setup_stdout_logger
from telemirror.notify import MAX_TEXT, BotNotifier, cut, failed_buttons
from telemirror.projects import Project, list_projects, load_chat_names, stats_path

logger = logging.getLogger("telemirror.report")

LIST_MAX = 10  # directions listed per section, then «…и ещё N»
TOP_ERRORS = 5
FILTER_SHARE, FILTER_MIN = 0.9, 10  # «almost everything»: ≥90% of ≥10 posts


def week(today: date) -> List[date]:
    """The 7 days before ``today`` (a Monday run: last Monday to Sunday)."""
    return [today - timedelta(days=n) for n in range(7, 0, -1)]


def _num(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def _pair(key: str, names: Dict[int, str]) -> str:
    source, target = stats.parse_pair(key)
    return f"{names.get(source) or source} → {names.get(target) or target}"


def _section(title: str, rows: List[str]) -> List[str]:
    out = [title, *(f"• {r}" for r in rows[:LIST_MAX])]
    if len(rows) > LIST_MAX:
        out.append(f"…и ещё {len(rows) - LIST_MAX}")
    return out


def report_text(key: str, today: Optional[date] = None) -> str:
    data = stats.load(key)
    days = week(today or date.today())
    names = load_chat_names(key)
    waiting = len(failed.load(key))
    lines = [f"📈 Сводка за неделю {days[0]:%d.%m}–{days[-1]:%d.%m}"]
    if not any(d.isoformat() in data["days"] for d in days):
        lines.append("Зеркало всю неделю не работало.")
    else:
        sums = stats.totals(data, days)
        sent, dropped, repeats, errors = (sum(col) for col in zip(*sums.values(), strict=True)) if sums \
            else (0, 0, 0, 0)
        lines.append(f"Скопировано: {_num(sent)} · отсеяно фильтрами: {_num(dropped)} · "
                     f"повторов: {_num(repeats)} · ошибок отправки: {_num(errors)}")
        configured = sorted(stats.pair_key(s, t) for s, t in data["pairs"])
        silent = [_pair(k, names) for k in configured if sum(sums.get(k, ())) == 0]
        if silent:
            lines += ["", *_section(f"🔇 Ничего не пришло за неделю ({len(silent)}):", silent)]
        worst = sorted(((v[3], k) for k, v in sums.items() if v[3]), reverse=True)[:TOP_ERRORS]
        if worst:
            lines += ["", *_section("⚠️ Больше всего ошибок отправки:",
                                    [f"{_pair(k, names)} — {_num(n)}" for n, k in worst])]
        heavy = []
        for k in sorted(sums):
            got = sums[k][0] + sums[k][1]
            if got >= FILTER_MIN and sums[k][1] >= FILTER_SHARE * got:
                heavy.append(f"{_pair(k, names)} — {round(100 * sums[k][1] / got)}% из {_num(got)}")
        if heavy:
            lines += ["", *_section("🧹 Фильтры отсеивают почти всё:", heavy)]
    if waiting:
        lines += ["", f"❗ Ждут повтора: {_num(waiting)} — кнопка ниже."]
    text = "\n".join(lines)
    # room for the label; UTF-16 units, as Telegram counts (notify.cut)
    return text if cut(text, MAX_TEXT - 100) == text else cut(text, MAX_TEXT - 101) + "…"


def send_reports(projects: List[Project], today: Optional[date] = None) -> Optional[bool]:
    """None: nothing to send (no project's mirror has counted anything yet)."""
    result: Optional[bool] = None
    for project in projects:
        if not stats_path(project.key).exists():
            continue
        notifier = BotNotifier.from_env(project.key, "live")
        if notifier is None:
            logger.warning("the panel's bot isn't set up (PANEL_BOT_TOKEN, PANEL_ADMIN_IDS): nobody to report to")
            return False
        markup = failed_buttons(project.key) if failed.load(project.key) else None
        sent = notifier.send_sync(report_text(project.key, today), markup)
        result = False if not sent or result is False else True
    return result


def main() -> None:
    setup_stdout_logger("telemirror", "INFO")
    sys.exit(1 if send_reports(list_projects()) is False else 0)


if __name__ == "__main__":
    main()
